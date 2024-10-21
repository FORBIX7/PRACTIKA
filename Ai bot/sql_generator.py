import requests
import re
import json


class SQLGenerator:

    def __init__(self, api_url="http://127.0.0.1:1234"):
        self.api_url = api_url

    def generate(self, query, tables_info):
        db_structure = {
            "tables": [
                {
                    "table_name": name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }
                for name, info in tables_info.items()
            ]
        }

        db_structure_json = json.dumps(db_structure, ensure_ascii=False, indent=2)

        prompt = (
            "You are an expert SQL developer specializing in SQLite databases. "
            "Your task is to generate correct SQL queries based on the provided database structure in response to user queries.\n\n"
            "Database structure:\n"
            f"<database_structure>\n"
            f"{db_structure_json}\n"
            f"</database_structure>\n\n"
            "Guidelines for generating the SQL query:\n"
            "1. Use only the tables and columns provided in the database structure.\n"
            "2. Ensure the query is syntactically correct for SQLite.\n"
            "3. Include appropriate JOIN clauses for multiple tables.\n"
            "4. Add WHERE clauses to filter results as needed.\n"
            "5. Utilize aggregation functions (COUNT, SUM, AVG, etc.) when relevant.\n"
            "6. Use ORDER BY for sorting results when applicable.\n"
            "7. Implement LIMIT if specified in the user's request.\n\n"
            "User's query:\n"
            f"<user_query>\n"
            f"{query}\n"
            f"</user_query>\n\n"
            "Generate the appropriate SQL query based on the above information. "
            "Output only the SQL query without explanations or comments. "
            "Используй язык и названия которые есть в базе данных"
            "Помести символ '-_-' перед SQL запросом"
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 400,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Clean the response
            model_response = re.sub(r'<\|.*?\|>', '', model_response)
            model_response = re.sub(r'SQL query:', '', model_response)
            model_response = re.sub(r'-_-', '', model_response)
            model_response = re.sub(
                r'```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|<generated_sql>\.|###\.|SQL\.|### <database_structure>|###|<database_structure>',
                '', model_response)
            model_response = model_response.lstrip('.').strip()  # Remove leading period and strip

            if "Ответ завершен" in model_response:
                model_response = model_response.split("Ответ завершен")[0]

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

            sql_queries = []
            current_query = ""

            for line in model_response.splitlines():
                line = line.strip()
                line = re.sub(r'--.*$', '', line).strip()  # Удаляем комментарии
                if not line or "Your Answer:" in line or "Ответ завершен." in line:
                    continue

                # Проверка на SQL команды с игнорированием пробелов в начале
                if re.match(r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)', line, re.IGNORECASE) or current_query:
                    current_query += " " + line.strip()
                else:
                    current_query += " " + line.strip()

                # Проверяем, если текущий запрос завершен
                if line.endswith(';') or current_query.endswith(';'):
                    sql_queries.append(current_query.strip())
                    current_query = ""

            # Добавление оставшегося запроса, если он есть
            if current_query:
                sql_queries.append(current_query.strip())

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