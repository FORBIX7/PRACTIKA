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
        """Отправляет запрос к модели API для генерации SQL-запроса."""
        if not self.tables_info:
            print("No tables loaded. Ensure the database contains tables and they are reflected.")
            return None

        db_structure = "\n".join([
            f"Table {name}: columns {', '.join(info['columns'].keys())}, "
            f"primary keys {', '.join(info['primary_keys'])}, "
            f"foreign keys {', '.join(info['foreign_keys'].keys())}"
            for name, info in self.tables_info.items()
        ])

        # Improved prompt
        prompt = (
            f"На основе следующей структуры базы данных:\n{db_structure}\n"
            f"Напиши ТОЛЬКО ОДИН SQL запрос к следующему сообщению пользователя: '{query}'.\n"
        )

        payload = {
            "model": "your_model",  # Замените на вашу модель
            "prompt": prompt,
            "max_tokens": 50,
            "temperature": 0.001  # Set low temperature for direct responses
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            print(f"Model Response: {model_response}")

            # Split model response into lines and look for SQL queries
            sql_queries = []
            # Define a set of SQL keywords to check for
            sql_keywords = {'INSERT', 'SELECT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'MERGE'}

            for line in model_response.splitlines():
                # Check if any keyword is present in the line (case insensitive)
                if any(keyword in line.upper() for keyword in sql_keywords):
                    sql_queries.append(line.strip())  # Add the entire line with the query

            if sql_queries:
                return sql_queries  # Return the list of detected SQL queries
            else:
                print("No valid SQL queries found in model response.")
                return None


        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
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
