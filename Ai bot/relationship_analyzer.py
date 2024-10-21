import requests
import re
import json


class RelationshipAnalyzer:

    def __init__(self, api_url="http://127.0.0.1:1234"):
        self.api_url = api_url

    def analyze(self, query, tables_info):
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
            "You are an AI model specializing in database structure analysis. Your task is to determine and establish logical connections "
            "between two specified tables based on a user query and the provided database structure.\n\n"

            "First, you will be given the database structure in JSON format:\n"
            f"<database_structure>\n{db_structure_json}\n</database_structure>\n\n"

            "Next, you will receive a user query:\n"
            f"<user_query>\n{query}\n</user_query>\n\n"

            "Analyze the database structure and the user query using the following rules:\n"
            "1. Prioritize direct connections through foreign keys if they exist.\n"
            "2. If there is no direct connection, look for indirect connections through intermediate tables.\n"
            "3. In the absence of explicit key-based connections, create logical connections based on the similarity of table and column names.\n"
            "4. All established connections must be logically justified and meaningful.\n\n"

            "After your analysis, return the result in the following JSON format:\n"
            '{\n'
            '  "relevant_tables": [\n'
            '    {\n'
            '      "table_name": "string",\n'
            '      "columns": [\n'
            '        {\n'
            '          "name": "string",\n'
            '          "data_type": "string"\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ],\n'
            '  "relationships": [\n'
            '    {\n'
            '      "table1": "string",\n'
            '      "table2": "string",\n'
            '      "relationship_type": "string",  // "direct", "indirect", "logical"\n'
            '      "joining_columns": {\n'
            '        "table1_column": "string",\n'
            '        "table2_column": "string"\n'
            '      },\n'
            '      "intermediate_table": "string",  // Fill only for "indirect" connections\n'
            '      "description": "string"  // Brief description of the connection\n'
            '    }\n'
            '  ]\n'
            '}\n\n'

            "Additional instructions:\n"
            "1. If relevant tables or connections are not found, clearly indicate this in your response.\n"
            "2. Provide a brief description for each established connection in the 'description' field.\n"
            "3. If the connection is indirect (through an intermediate table), specify this table in the 'intermediate_table' field.\n"
            "4. Ensure that all established connections correspond to the context of the user query.\n"
            "5. When creating logical connections, base them on the semantic proximity of table and column names.\n\n"

            "Before providing your final output, use a <scratchpad> to think through your analysis process. Consider the following steps:\n"
            "1. Identify the key elements in the user query.\n"
            "2. Scan the database structure for tables that might be relevant to these elements.\n"
            "3. Look for direct connections between these tables through foreign keys.\n"
            "4. If direct connections aren't found, consider indirect connections through intermediate tables.\n"
            "5. In the absence of key-based connections, think about logical connections based on naming conventions.\n"
            "6. Evaluate whether the identified connections make sense in the context of the user query.\n\n"

            "After your analysis, provide your final output in the JSON format"
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 2000,
            "temperature": 0
        }

        try:

            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()


            model_response = re.sub(r'^.*?({)', r'\1', model_response, flags=re.DOTALL).strip()


            model_response = model_response.split("Ответ завершен")[0].strip()
            model_response = model_response.split("</answer>")[0].strip()

            if not model_response or not model_response.startswith('{'):
                print("Некорректный ответ от ИИ.")
                return None

            try:
                tables_and_relationships = json.loads(model_response)
            except json.JSONDecodeError as e:
                print(f"Ошибка при разборе JSON: {e}")
                print("Текст ответа:")
                print(model_response)
                return None

            print(model_response)

            return tables_and_relationships


        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None