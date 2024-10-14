import requests
import re
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy_schemadisplay import create_schema_graph
from sqlalchemy.orm import configure_mappers
from PIL import Image


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
            "'sql_generation' for SQL query generation requests, "
            "'general_db_info' for general database information requests, and "
            "'narrow_query' for specific questions that require executing an SQL query and analyzing the result "
            "to provide an answer to the user's question.\n\n"
            "User's query:\n"
            f"{query}\n\n"
            "Output only the category (either 'sql_generation', 'general_db_info', or 'narrow_query') without any "
            "additional explanations."
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
            classification = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL',
    '', classification).strip()

            print(f"Classification: {classification}")  # Add this line to help with debugging
            return classification

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def generate_er_diagram(self, output_file="er_diagram.png", output_format="png", log=False):
        if not self.metadata.tables:
            print("Нет данных для создания диаграммы. Загрузите базу данных.")
            return

        # Настраиваем маппинг SQLAlchemy
        configure_mappers()

        try:
            # Логирование начального состояния
            if log:
                print("Начинаем создание ER-диаграммы...")

            # Создаем граф ER-диаграммы
            graph = create_schema_graph(
                metadata=self.metadata,
                engine=self.engine,  # Передаем движок базы данных
                show_datatypes=True,  # Показывать типы данных
                show_indexes=False,  # Не показывать индексы
                rankdir='LR',  # Направление диаграммы слева направо
                concentrate=True  # Упрощение диаграммы
            )

            # Экспортируем диаграмму в формат .dot
            dot_file = "er_diagram.dot"
            graph.write(dot_file, format="dot")
            print(f"ER-диаграмма сохранена в формате .dot: {dot_file}")

            # Модифицируем .dot файл для добавления стиля (цвет, шрифт, расстояния и т.д.)
            with open(dot_file, "r") as file:
                dot_data = file.read()

            # Добавляем кастомные стили и настройки
            styled_dot_data = dot_data.replace(
                'node [label=',
                'node [shape=box, style=filled, color=lightblue, fontcolor=black, fontsize=12, fontname=Helvetica, label='
            ).replace(
                'edge [',
                'edge [color=gray, fontsize=10, fontname=Helvetica, '
            ).replace(
                'graph [',
                'graph [size="10,10!", dpi=300, ranksep=1.5, nodesep=1.0, '  # Увеличиваем расстояния и разрешение
            )

            # Перезаписываем .dot файл с новыми стилями
            with open(dot_file, "w") as file:
                file.write(styled_dot_data)

            # Конвертируем .dot файл в нужный формат (например, PNG)
            output_file_with_extension = f"{output_file}.{output_format}"
            from subprocess import run
            run(["dot", "-T", output_format, dot_file, "-o", output_file_with_extension])

            print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")

            # Открываем изображение для отображения
            img_display = Image.open(output_file_with_extension)
            img_display.show()

            if log:
                print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")

        except ImportError as e:
            print("Необходимо установить pygraphviz для генерации диаграмм.")
            print(f"Ошибка: {e}")
        except Exception as e:
            print(f"Ошибка при создании ER-диаграммы: {e}")
            if log:
                print("Проверьте настройки подключения к базе данных и целостность данных.")

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
            "В конце ответа напиши 'Ответ завершен.'"
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

            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL',
    '',
                model_response
            ).strip()

            # Обрезаем текст после слов "Ответ завершен."
            if "Ответ завершен" in model_response:
                model_response = model_response.split("Ответ завершен")[0] + "Ответ завершен."

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
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 600,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Улучшенная фильтрация ненужного текста
            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL',
    '',
                model_response
            ).strip()

            # Обрезаем текст после слов "Ответ завершен."
            model_response = model_response.split("Ответ завершен")[0] + "Ответ завершен."

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def analyze_sql_result(self, sql_result, query):
        """Отправляет результат SQL-запроса в ИИ для анализа и получения окончательного ответа."""
        if not sql_result:  # Обработка пустого результата
            return "Нет данных для анализа."

        result_string = "\n".join([str(row) for row in sql_result])

        prompt = (
            "You are a highly skilled database expert with deep knowledge of SQL queries and data analysis. "
            "Your task is to interpret the provided SQL query result and answer the user's question in a clear, precise, and concise manner.\n\n"
            "Here is the result of the SQL query:\n"
            f"{result_string}\n\n"
            "The user's question is:\n"
            f"{query}\n\n"
            "Based on the SQL query result, respond to the user with an accurate, concise, and contextually relevant explanation. "
            "Ensure your answer directly addresses the user's question.\n\n"
            "Consider the following guidelines when crafting your response:\n"
            "- If the query result contains data, provide a well-structured and insightful answer, highlighting key findings and patterns if necessary.\n"
            "- If the result set is empty or no relevant data is found, clearly explain that no data was retrieved, and offer potential reasons or next steps if appropriate.\n"
            "- Avoid including unnecessary technical jargon, focusing on clarity and simplicity.\n"
            "- If any additional assumptions or clarifications are needed to address the user's query, mention them explicitly in your answer."
            "Write on Russia language"
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 200,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            analysis = response.json().get('choices', [{}])[0].get('text', '').strip()
            return analysis

        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе: {e}")
            return None

    def clean_ai_response(self, response_text):
        """Очищает вывод ИИ от ненужных символов и текстовых артефактов."""
        # Убираем все технические теги, вроде <|end_of_text|> и подобных
        cleaned_text = re.sub(r'<\|.*?\|>', '', response_text)

        # Убираем лишние символы вроде URL-подобных строк
        cleaned_text = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL',
    '', cleaned_text)

        # Удаляем пустые строки и лишние пробелы
        cleaned_text = "\n".join([line.strip() for line in cleaned_text.splitlines() if line.strip()])

        # Обрезаем текст после слов "Ответ завершен."
        cleaned_text = cleaned_text.split("Ответ завершен")[0] + "Ответ завершен."

        return cleaned_text

    def narrow_query_analyzer(self, query):
        """Обрабатывает узконаправленные запросы с выполнением SQL и анализом результата."""
        sql_queries = self.generate_sql(query)

        if not sql_queries:
            print("Не удалось сгенерировать SQL-запрос.")
            return None

        with self.engine.connect() as connection:
            try:
                for sql_query in sql_queries:
                    result = connection.execute(sa.text(sql_query))

                    if result.returns_rows:
                        rows = result.fetchall()

                        # Если данные найдены, отправляем их на анализ
                        analysis = self.analyze_sql_result(rows, query)
                    else:
                        analysis = self.analyze_sql_result([], query)  # Пустой список

                    # Очищаем ответ ИИ — передаем только сам текст
                    cleaned_analysis = self.clean_ai_response(analysis)

                    if cleaned_analysis:  # Проверяем на None
                        print(f"\nОтвет на ваш запрос: {cleaned_analysis}")
                    else:
                        print("Не удалось получить ответ от ИИ.")

            except SQLAlchemyError as e:
                print(f"Ошибка выполнения SQL-запроса: {e}")



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
    try:
        agent = SQLAgent(db_url)
        print("Подключение к базе данных успешно.")
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        exit(1)

    while True:
        try:
            # Отображение информации о таблицах базы данных
            agent.display_tables_info()

            # Получение запроса от пользователя
            user_query = input("Введите ваш запрос (или напишите 'exit' для выхода): ").strip().lower()

            # Выход, если пользователь вводит 'exit'
            if user_query == 'exit':
                print("Завершение программы.")
                break

            # Обработка запросов, связанных с диаграммами
            if 'диаграмм' in user_query:
                agent.generate_er_diagram()  # Генерация ER-диаграммы
            else:
                query_type = agent.classify_query(user_query)

                # Обработка SQL-запросов
                if 'sql_generation' in query_type:
                    print("Classification: Генерация SQL запроса")
                    sql_queries = agent.generate_sql(user_query)

                    if sql_queries:
                        agent.execute_sql_queries(sql_queries)
                    else:
                        print("Не удалось сгенерировать SQL-запрос.")

                # Обработка запросов, связанных с общей информацией о базе данных
                elif 'general_db_info' in query_type:
                    print("Classification: Общий вопрос")
                    agent.generate_info(user_query)
                elif 'narrow_query' in query_type:
                    print("Classification: узконаправленный запрос")
                    agent.narrow_query_analyzer(user_query)


                # Обработка неклассифицированных запросов
                else:
                    print("Не удалось классифицировать запрос.")

        except Exception as e:
            print(f"Произошла ошибка: {e}")

        # Запрос на продолжение или выход
        print("==============================")
        if input("Напишите 'exit', чтобы выйти, или нажмите Enter для продолжения... ").strip().lower() == "exit":
            break
        print("==============================")

    print("Программа завершена.")
