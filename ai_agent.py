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

    def generate_er_diagram(self):
        """Генерация ER-диаграммы базы данных с использованием Graphviz."""
        if not self.metadata.tables:
            print("Нет данных для создания диаграммы. Загрузите базу данных.")
            return

        configure_mappers()  # Настраиваем маппинг SQLAlchemy

        try:
            # Создаем граф ER-диаграммы
            graph = create_schema_graph(metadata=self.metadata,
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
            "Ты — эксперт по SQL для базы данных на SQLite. Твоя задача — на основе предоставленной структуры базы данных генерировать только правильные SQL-запросы в ответ на запрос пользователя. Структура базы данных:\n"
            f"{db_structure}\n\n"
            "Ответь только SQL-запросом без дополнительных пояснений или комментариев. Запрос пользователя:\n"
            f"'{query}'\n"
            "Выведи корректный SQL-запрос."
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 100,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Улучшенная фильтрация лишнего текста
            model_response = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]', '',
                                    model_response).strip()

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

            sql_queries = []
            current_query = ""

            # Обработка ответа модели
            for line in model_response.splitlines():
                line = line.strip()
                if line:

                    # Удаляем SQL-комментарии
                    line = re.sub(r'--.*$', '', line).strip()  # Удаляем однострочные комментарии

                    # Проверяем на корректный SQL-запрос
                    if re.match(r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)', line, re.IGNORECASE):
                        if current_query:
                            sql_queries.append(current_query.strip())
                        current_query = line
                    else:
                        current_query += " " + line

                    # Проверка на завершение запроса
                    if current_query.endswith(';'):  # Проверяем на точку с запятой
                        sql_queries.append(current_query.strip())
                        current_query = ""

            # Исключение пустых строк и некорректных SQL-запросов
            sql_queries = [sql for sql in sql_queries if sql]

            if sql_queries:
                print("\n=== Сгенерированные SQL-запросы ===")
                for idx, sql in enumerate(sql_queries, 1):
                    print(f"{idx}. {sql}")
                print("==============================\n")
                return sql_queries
            else:
                print("Не удалось найти корректные SQL-запросы в ответе модели.")
                return None

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
    db_url = 'sqlite:///12.db'
    agent = SQLAgent(db_url)

    agent.display_tables_info()

    user_query = input("Введите ваш запрос: ")
    if 'диаграмм' in user_query.lower():
        agent.generate_er_diagram()  # Генерация ER-диаграммы
    else:
        sql_queries = agent.generate_sql(user_query)

        if sql_queries:
            agent.execute_sql_queries(sql_queries)
        else:
            print("Не удалось сгенерировать SQL-запрос.")

    print("Завершение программы.")

