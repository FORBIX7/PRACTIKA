import requests
import re
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


class SQLAgent:
    def __init__(self, db_url, api_url="http://127.0.0.1:1234"):
        self.engine = sa.create_engine(db_url)
        self.metadata = sa.MetaData()
        self.tables_info = {}
        self.api_url = api_url
        self.load_database()

    def load_database(self):
        """Загрузка и анализ структуры базы данных."""
        try:
            self.metadata.reflect(bind=self.engine)  # Reflect database structure
        except SQLAlchemyError as e:
            print(f"Error reflecting database structure: {e}")

        if not self.metadata.tables:
            print("No tables found in the database. Please check your database.")
            return

        for table_name in self.metadata.tables:
            table = self.metadata.tables[table_name]
            self.tables_info[table_name] = {
                'columns': {col.name: str(col.type) for col in table.columns},
                'primary_keys': [col.name for col in table.primary_key],
                'foreign_keys': {fk.column: str(fk.target_full) for fk in table.foreign_keys}
            }
        print("Database loaded. Available tables:", list(self.tables_info.keys()))

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
            "max_tokens": 60,  # Увеличил количество токенов для ответа
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
        """Executes the generated SQL queries in the database and outputs the result of the change."""
        with self.engine.connect() as connection:
            for query in queries:
                try:
                    if query and query.endswith(";"):  # Check if the query is complete
                        print(f"Executing query: {query}")
                        result = connection.execute(sa.text(query))
                        if result.returns_rows:
                            for row in result:
                                print(row)
                        else:
                            connection.commit()  # Commit the transaction for insert/update
                            print(f"Query executed successfully: {query}")
                except SQLAlchemyError as e:
                    print(f"Error executing query: {e}")

    def display_tables_info(self):
        """Вывод информации о всех таблицах в базе данных."""
        if not self.tables_info:
            print("No tables available.")
        for table_name, info in self.tables_info.items():
            print(f"\nTable: {table_name}")
            print("Columns:", info['columns'])
            print("Primary Keys:", info['primary_keys'])
            print("Foreign Keys:", info['foreign_keys'])


# Пример использования
if __name__ == '__main__':
    db_url = 'sqlite:///12.db'  # Укажите путь к вашей локальной БД
    agent = SQLAgent(db_url)

    # Вывод информации о таблицах в базе данных
    agent.display_tables_info()

    # Пример генерации SQL-запроса от пользователя
    user_query = input("Введите ваш запрос (например, 'Создай пользователя Саша 40 лет'): ")
    sql_queries = agent.generate_sql(user_query)

    if sql_queries:
        print(f"Сгенерированные SQL-запросы: {sql_queries}")
        agent.execute_sql_queries(sql_queries)  # Execute all detected SQL queries
    else:
        print("Не удалось сгенерировать SQL-запрос.")

    # Завершение программы
    print("Завершение программы.")
