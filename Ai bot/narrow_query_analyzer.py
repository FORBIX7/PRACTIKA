import requests
import re


class NarrowQueryAnalyzer:

    def __init__(self, api_url="http://127.0.0.1:1234"):
        self.api_url = api_url

    def analyze(self, query, sql_result):

        if not sql_result:
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
            "Отвечай на русском языке"
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 300,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            analysis = response.json().get('choices', [{}])[0].get('text', '').strip()
            if "Ответ завершен" in analysis:
                analysis = analysis.split("Ответ завершен")[0]
            return analysis


        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе: {e}")
            return None