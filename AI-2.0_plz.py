import requests
import re
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy_schemadisplay import create_schema_graph
from sqlalchemy.orm import configure_mappers


class SQLAgent:
    def __init__(self, db_url, api_url="http://127.0.0.1:1234"):
        self.engine = sa.create_engine(db_url)
        self.metadata = sa.MetaData()
        self.tables_info = {}
        self.api_url = api_url
        self.load_database()

    def classify_query(self, query):
        """Отправляет запрос к модели API для классификации вопроса."""
        prompt = (
            "You are an AI model specialized in classifying questions related to databases. "
            "Classify the following user query into one of the following categories: "
            "'sql_generation' for SQL query generation requests, and 'general_db_info' for general database "
            "information requests.\n\n"
            "User's query:\n"
            f"{query}\n\n"
            "Output only the category (either 'sql_generation' or 'general_db_info') without any additional "
            "explanations."
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 20,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            classification = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Clean up the classification response
            classification = re.sub(r'<\|.*?\|>', '', classification).strip()

            print(f"Classification: {classification}")  # Add this line to help with debugging
            return classification

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def generate_er_diagram(self):
        """Генерация ER-диаграммы базы данных с использованием Graphviz."""
        if not self.metadata.tables:
            print("Нет данных для создания диаграммы. Загрузите базу данных.")
            return

        configure_mappers()  # Настраиваем маппинг SQLAlchemy

        try:
            # Создаем граф ER-диаграммы
            graph = create_schema_graph(metadata=self.metadata,
                                        engine=self.engine,  # Передаем движок базы данных
                                        show_datatypes=True,  # Показывать типы данных
                                        show_indexes=False,  # Не показывать индексы
                                        rankdir='LR',  # Направление диаграммы слева направо
                                        concentrate=False)  # Упрощение диаграммы

            # Сохраняем диаграмму в файл
            diagram_file = "er_diagram.png"
            graph.write_png(diagram_file)

            print(f"ER-диаграмма успешно создана и сохранена в файл: {diagram_file}")

        except Exception as e:
            print(f"Ошибка при создании ER-диаграммы: {e}")

    def load_database(self):
        """Загрузка и анализ структуры базы данных."""
        try:
            self.metadata.reflect(bind=self.engine)  # Reflect database structure
        except SQLAlchemyError as e:
            print(f"Ошибка при загрузке структуры базы данных: {e}")

        if not self.metadata.tables:
            print("Таблицы отсутствуют в базе данных. Проверьте базу данных.")
            return

        for table_name in self.metadata.tables:
            table = self.metadata.tables[table_name]
            self.tables_info[table_name] = {
                'columns': {col.name: str(col.type) for col in table.columns},
                'primary_keys': [col.name for col in table.primary_key],
                'foreign_keys': {fk.column.name: str(fk.target_fullname) for fk in table.foreign_keys}
            }
        print("\n=== База данных загружена. Доступные таблицы ===")
        print(list(self.tables_info.keys()))
        print("===============================================\n")

    def generate_sql(self, query):
        """Отправляет запрос к модели API для генерации SQL-запроса и выводит структурированный результат."""
        if not self.tables_info:
            print("База данных пуста. Начните с создания первой таблицы.")
            return None

        db_structure = "\n".join([
            f"Таблица {name}: колонки {', '.join(info['columns'].keys())}, "
            f"первичные ключи {', '.join(info['primary_keys'])}, "
            f"внешние ключи {', '.join(info['foreign_keys'].keys())}"
            for name, info in self.tables_info.items()
        ])

        prompt = (
            "You are an expert SQL developer specializing in SQLite databases. "
            "Your task is to generate correct SQL queries based on the provided database structure in response to user queries.\n\n"
            "Here is the structure of the database:\n"
            f"<database_structure>\n"
            f"{db_structure}\n"
            f"</database_structure>\n\n"
            "Your task is to generate a correct SQL query that addresses the user's request. Follow these guidelines:\n\n"
            "1. Use only the tables and columns provided in the database structure.\n"
            "2. Ensure your query is syntactically correct for SQLite.\n"
            "3. Use appropriate JOIN clauses when querying multiple tables.\n"
            "4. Include WHERE clauses as necessary to filter results.\n"
            "5. Use aggregation functions (COUNT, SUM, AVG, etc.) when appropriate.\n"
            "6. Order results using ORDER BY if it makes sense for the query.\n"
            "7. Limit results using LIMIT if specified in the user's request.\n\n"
            "The user's query is:\n"
            f"<user_query>\n"
            f"{query}\n"
            f"</user_query>\n\n"
            "Based on the database structure and the user's query, generate the appropriate SQL query. "
            "Output only the SQL query without any additional explanations or comments."
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 200,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Улучшенная фильтрация ненужного текста
            model_response = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]', '',
                                    model_response).strip()

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

            sql_queries = []
            current_query = ""

            # Обработка ответа модели, включая многострочные запросы
            for line in model_response.splitlines():
                line = line.strip()
                # Удаляем однострочные комментарии
                line = re.sub(r'--.*$', '', line).strip()
                if not line:  # Пропускаем пустые строки
                    continue

                # Проверяем на корректный SQL-запрос
                if re.match(r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)', line, re.IGNORECASE):
                    if current_query:
                        current_query += " " + line
                    else:
                        current_query = line
                else:
                    current_query += " " + line

                # Проверка на завершение запроса
                if current_query.endswith(';'):
                    sql_queries.append(current_query.strip())
                    current_query = ""

            # Исключение пустых строк и некорректных SQL-запросов
            sql_queries = [sql for sql in sql_queries if sql]

            # Удаление дубликатов запросов
            unique_sql_queries = list(set(sql_queries))

            if unique_sql_queries:
                print("\n=== Сгенерированные SQL-запросы ===")
                for idx, sql in enumerate(unique_sql_queries, 1):
                    print(f"{idx}. {sql.strip(';')}")
                print("==============================\n")
                return unique_sql_queries
            else:
                print("Не удалось найти корректные SQL-запросы в ответе модели.")
                return None

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None


    def generate_info(self, query):
        """Отправляет запрос к модели API для генерации и выводит информацию."""
        if not self.tables_info:
            print("База данных пуста. Начните с создания первой таблицы.")
            return None

        db_structure = "\n".join([
            f"Таблица {name}: колонки {', '.join(info['columns'].keys())}, "
            f"первичные ключи {', '.join(info['primary_keys'])}, "
            f"внешние ключи {', '.join(info['foreign_keys'].keys())}"
            for name, info in self.tables_info.items()
        ])

        prompt = (
            "You are an expert in relational database systems, specializing in analyzing and explaining database structures. "
            "Your task is to provide accurate and detailed answers to user questions about the given database based on its structure.\n\n"
            "Here is the structure of the database:\n"
            f"<database_structure>\n"
            f"{db_structure}\n"
            f"</database_structure>\n\n"
            "Your task is to answer the user's question clearly and concisely. Follow these guidelines:\n\n"
            "1. Refer to only the tables and columns provided in the database structure.\n"
            "2. Ensure your answer is accurate and relevant to the user's question.\n"
            "3. Provide explanations where necessary to clarify the relationships between tables or data points.\n"
            "4. Use technical terms appropriately, but keep the explanation clear and easy to understand.\n"
            "5. Include examples or summaries if it helps to illustrate the answer.\n\n"
            "The user's question is:\n"
            f"<user_question>\n"
            f"{query}\n"
            f"</user_question>\n\n"
            "Based on the database structure and the user's question, provide a detailed and accurate answer. "
            "Output only the answer without any additional comments or explanations outside of the context of the user's query."
            "Write on Russia language"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 1000,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Улучшенная фильтрация ненужного текста
            model_response = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]', '',
                                    model_response).strip()

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None


    def execute_sql_queries(self, queries):
        """Выполнение сгенерированных SQL-запросов и вывод результата."""
        with self.engine.connect() as connection:
            inspector = inspect(self.engine)
            for query in queries:
                try:
                    if query.startswith("CREATE TABLE"):
                        table_name = re.search(r'CREATE TABLE (\w+)', query).group(1)
                        existing_tables = inspector.get_table_names()
                        if table_name in existing_tables:
                            print(f"Таблица '{table_name}' уже существует. Пропуск запроса: {query}")
                            continue

                    if query and query.endswith(";"):
                        print(f"\n=== Выполняется запрос ===\n{query}")
                        result = connection.execute(sa.text(query))

                        if result.returns_rows:
                            rows = result.fetchall()
                            if rows:
                                print("\n=== Результат выполнения запроса (всего строк: {}): ===".format(len(rows)))
                                for row in rows:
                                    print(row)
                                print("===============================\n")
                            else:
                                print("\n=== Запрос выполнен, но данные не найдены. ===\n")
                        else:
                            connection.commit()  # Коммитим изменения для запросов, не возвращающих данные
                            print("Запрос выполнен успешно!")
                except SQLAlchemyError as e:
                    print(f"Ошибка выполнения запроса: {e}")
        print("Выполнение запросов завершено.")

    def display_tables_info(self):
        """Вывод информации о всех таблицах в базе данных."""
        if not self.tables_info:
            print("Таблицы отсутствуют в базе данных.")
            return

        print("\n" + "=" * 50)
        print("Информация о таблицах в базе данных:")
        print("=" * 50)

        for table_name, info in self.tables_info.items():
            print(f"\nТаблица: {table_name}")
            print("-" * 50)
            print(f"{'Колонки:':<15}",
                  ", ".join([f"{col_name} ({col_type})" for col_name, col_type in info['columns'].items()]))
            print(f"{'Первичные ключи:':<15}", ", ".join(info['primary_keys']) if info['primary_keys'] else "Нет")
            if info['foreign_keys']:
                print(f"{'Внешние ключи:':<15}",
                      ", ".join([f"{col} -> {fk}" for col, fk in info['foreign_keys'].items()]))
            else:
                print(f"{'Внешние ключи:':<15} Нет")
            print("-" * 50)

        print("\nКонец списка таблиц.")
        print("=" * 50)


# Пример использования
if __name__ == '__main__':
    db_url = 'sqlite:///chinook.db'
    agent = SQLAgent(db_url)

    while (1):
        agent.display_tables_info()

        user_query = input("Введите ваш запрос: ")
        if 'диаграмм' in user_query.lower():
            agent.generate_er_diagram()  # Генерация ER-диаграммы
        else:
            query_type = agent.classify_query(user_query)

            if 'sql_generation' in query_type:
                print("Classification: sql_generation")
                sql_queries = agent.generate_sql(user_query)

                if sql_queries:
                    agent.execute_sql_queries(sql_queries)
                else:
                    print("Не удалось сгенерировать SQL-запрос.")
            elif 'general_db_info' in query_type:
                print("Classification: general_db_info")
                agent.generate_info(user_query)  # Здесь можно добавить обработку других вопросов о БД
            else:
                print("Не удалось классифицировать запрос.")


        print("==============================")
        if "exit" == input("Напишите 'exit', чтобы выйти или нажмите Enter, чтобы продолжить...   "):
            break
        print("==============================")

    print("Завершение программы.")