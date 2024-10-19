import requests
import re


class QueryClassifier:

    def __init__(self, api_url="http://127.0.0.1:1234"):
        self.api_url = api_url

    def classify(self, query):
        prompt = (
            "You are an AI model designed to classify user queries about databases. Your goal is to analyze the query and categorize it with precision into one of the following categories:\n"
            "'sql_generation' – for requests to generate SQL queries from scratch;\n"
            "'general_db_info' – for general database information or theoretical knowledge about databases, which does not require running or analyzing specific queries;\n"
            "'narrow_query' – for detailed questions that require executing SQL queries or performing data analysis to provide an answer.\n\n"
            "Important: If the query asks for specific information that requires analyzing or extracting data from a database (such as a genre analysis or specific metrics), it should be classified as 'narrow_query'. General theoretical questions about databases fall under 'general_db_info'.\n\n"
            "User's query:\n"
            f"{query}\n\n"
            "Classify the query with precision. Output only one of the following: 'sql_generation', 'general_db_info', or 'narrow_query'. No explanations or additional text."
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

            classification = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
                                    '', classification).strip()

            print(f"Classification: {classification}")
            return classification

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None