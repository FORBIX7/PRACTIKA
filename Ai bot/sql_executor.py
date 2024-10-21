import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
import re  # Importing the re module for regular expressions


class SQLExecutor:
    def __init__(self, engine):
        self.engine = engine

    def process_case_insensitive(self, query):
        """
        Преобразует строковые условия WHERE в регистронезависимые, используя LOWER().
        Например, WHERE City = 'calgary' -> WHERE LOWER(City) = LOWER('calgary')
        """
        # Регулярное выражение для поиска условий WHERE
        pattern = re.compile(r"(WHERE\s+)(\w+)(\s*=\s*)'([^']*)'", re.IGNORECASE)

        # Замена условий на LOWER(field) = LOWER('value')
        def repl(match):
            return f"{match.group(1)}LOWER({match.group(2)}){match.group(3)}LOWER('{match.group(4)}')"

        # Применение преобразования
        return pattern.sub(repl, query)

    def execute(self, queries):
        with self.engine.connect() as connection:
            inspector = inspect(self.engine)
            for query in queries:
                try:
                    # Проверка на CREATE TABLE и существование таблицы
                    if query.startswith("CREATE TABLE"):
                        table_name = re.search(r'CREATE TABLE (\w+)', query).group(1)
                        existing_tables = inspector.get_table_names()
                        if table_name in existing_tables:
                            print(f"Таблица '{table_name}' уже существует. Пропуск запроса: {query}")
                            continue

                    # Преобразование строки запроса для регистронезависимых сравнений
                    query = self.process_case_insensitive(query)

                    if query.strip().endswith(";"):
                        query = query.strip()  # Убираем пробелы и символы в начале и конце
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
                            connection.commit()
                            print("Запрос выполнен успешно!")
                except SQLAlchemyError as e:
                    print(f"Ошибка выполнения запроса: {e}")
        print("Выполнение запросов завершено.")