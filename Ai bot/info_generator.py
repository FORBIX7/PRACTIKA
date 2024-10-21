import requests
import re
import json

class InfoGenerator:
    def __init__(self, api_url="http://127.0.0.1:1234"):
        self.api_url = api_url


    def generate(self, query, tables_info):
        if not tables_info:
            print("База данных пуста. Начните с создания первой таблицы.")
            return None

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
            "You are an expert in relational database systems, specializing in analyzing and explaining database structures. "
            "Your task is to provide accurate and detailed answers to user questions about the given database based on its structure.\n\n"
            "Here is the structure of the database:\n"
            f"<database_structure>\n"
            f"{db_structure_json}\n"
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
            "max_tokens": 600,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()


            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
                '',
                model_response
            ).strip()


            model_response = model_response.split("Ответ завершен")[0] + "Ответ завершен."

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None