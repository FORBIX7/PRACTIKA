import json
import pydot
from subprocess import run
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer
import graphviz
from subprocess import run
from PIL import Image
import openai
import requests
import re
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy_schemadisplay import create_schema_graph
from sqlalchemy.orm import configure_mappers
from PIL import Image
import os

class SQLAgent:
    def __init__(self, database_url, openai_api_key, proxy_host, proxy_port, proxy_username, proxy_password):
        self.database_engine = sa.create_engine(database_url)
        self.database_metadata = sa.MetaData()
        self.tables_information = {}
        self.openai_api_key = openai_api_key
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.proxy_string = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
        os.environ['HTTP_PROXY'] = self.proxy_string
        os.environ['HTTPS_PROXY'] = self.proxy_string
        openai.proxy = self.proxy_string
        self.load_database()

    def chatgpt_request(self, prompt, maximum_tokens=20, temperature=0):
        openai.api_key = self.openai_api_key
        try:
            response = openai.ChatCompletion.create(  # Use ChatCompletion
                model="gpt-4o-mini",  # Specify the model name directly
                messages=[{"role": "user", "content": prompt}],  # Messages in chat format
                max_tokens=maximum_tokens,
                n=1,
                stop=None,
                temperature=temperature
            )
            if response and response.choices and response.choices[0].message.content:  # Access content correctly
                return response.choices[0].message.content.strip()
            else:
                print("Empty response from OpenAI API.")
                return None
        except openai.error.RateLimitError as e:
            print(f"OpenAI Rate Limit Error: {e}")
            return None
        except openai.error.APIError as e:
            print(f"OpenAI API Error: {e}")
            return None
        except openai.error.ServiceUnavailableError as e:
            print(f"OpenAI Service Unavailable: {e}")
            return None
        except openai.error.OpenAIError as error:
            print(f"Ошибка ChatGPT API: {error}")
            return None
        except Exception as error:
            print(f"An unexpected error occurred: {error}")
            return None

    def classify_query(self, query):
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
        try:
            classification = self.chatgpt_request(prompt, maximum_tokens=20, temperature=0)
            classification = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
                '',
                classification
            ).strip()
            print(f"Classification: {classification}")
            return classification
        except Exception as error:
            print(f"Произошла ошибка при запросе: {error}")
            return None

    def analyze_query_for_relationships(self, query):
        db_structure = {
            "tables": [
                {
                    "table_name": name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }
                for name, info in self.tables_information.items()
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
            "max_tokens": 800,
            "temperature": 0
        }
        try:
            model_response = self.chatgpt_request(prompt, maximum_tokens=2000, temperature=0)
            model_response = re.sub(r'^.*?({)', r'\1', model_response, flags=re.DOTALL).strip()
            model_response = model_response.split("Ответ завершен")[0].strip()
            model_response = model_response.split("</answer>")[0].strip()
            if not model_response or not model_response.startswith('{'):
                print("Некорректный ответ от ИИ.")
                return None
            try:
                tables_and_relationships = json.loads(model_response)
            except json.JSONDecodeError as error:
                print(f"Ошибка при разборе JSON: {error}")
                print("Текст ответа:")
                print(model_response)
                return None
            print(model_response)
            if not self.database_metadata.tables:
                print("Нет данных для создания диаграммы. Загрузите базу данных.")
                return
            configure_mappers()
            try:
                self.generate_er_diagram(tables_and_relationships)
            except ImportError as error:
                print("Необходимо установить pygraphviz для генерации диаграмм.")
                print(f"Ошибка: {error}")
            except Exception as error:
                print(f"Ошибка при создании ER-диаграммы: {error}")
        except Exception as error:
            print(f"Произошла ошибка при запросе: {error}")
            return None


    def generate_er_diagram(self, tables_and_relationships, output_file="er_diagram_auto", output_format="png", log=True, relationship_styles=None):
        print("Результат анализа запроса:")
        print(tables_and_relationships)
        relevant_tables = [table["table_name"] for table in tables_and_relationships.get("relevant_tables", [])]
        relationships = tables_and_relationships.get("relationships", [])
        relevant_metadata = MetaData()
        for table_info in tables_and_relationships["relevant_tables"]:
            table_name = table_info["table_name"]
            if table_name in self.database_metadata.tables:
                print(f"Добавление таблицы: {table_name}")
                Table(table_name, relevant_metadata, autoload_with=self.database_engine)
        print("Таблицы в relevant_metadata после добавления:", relevant_metadata.tables.keys())
        try:
            print("Создание графа ER-диаграммы...")
            graph = graphviz.Digraph('ER Diagram', format=output_format)
            graph.attr(rankdir='LR', concentrate='true', size="10,10!", dpi="300", nodesep="1.0", ranksep="1.5")
        except Exception as error:
            print(f"Ошибка при создании ER-диаграммы: {str(error)}")
            return
        if relationship_styles is None:
            relationship_styles = {
                'one-to-many': {"style": "solid", "color": "black"},
                'many-to-many': {"style": "dashed", "color": "green"},
                'possible': {"style": "dotted", "color": "blue"},
            }
        for table in relevant_tables:
            print(f"Добавление узла для таблицы: {table}")
            columns = [
                f"- {column['name']} : {column['data_type'].upper()}"
                for column in tables_and_relationships['relevant_tables'][relevant_tables.index(table)]['columns']
            ]
            table_label = f"{{ {table} | {{ | {' | '.join(columns)} }} }}"
            graph.node(table, label=table_label, shape="record", style="filled", color="lightblue", fontname="Helvetica", fontsize="12")
        print("Таблицы в метаданных:")
        print(self.database_metadata.tables.keys())
        for relationship in relationships:
            table1 = relationship['table1']
            table2 = relationship['table2']
            print(f"Обработка связи: {table1} -> {table2}")
            if table1 in relevant_tables and table2 in relevant_tables:
                table1_column = relationship['joining_columns']['table1_column']
                table2_column = relationship['joining_columns']['table2_column']
                label = f"{table1}.{table1_column} -> {table2}.{table2_column}"
                relationship_type = relationship.get('relationship_type', 'one-to-many')
                style = relationship_styles.get(relationship_type, {"style": "solid", "color": "black"})
                print(f"Добавление связи: {label}")
                graph.edge(f"{table1}:{table1_column}", f"{table2}:{table2_column}", label=label, style=style["style"], color=style["color"])

        dot_file = f"{output_file}.dot"
        graph.save(dot_file)
        print(f"ER-диаграмма сохранена в формате .dot: {dot_file}")
        output_file_with_extension = f"{output_file}.{output_format}"
        graph.render(filename=output_file_with_extension, cleanup=True)
        print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")
        image_display = Image.open(f"{output_file}.{output_format}.{output_format}")
        image_display.show()
        if log:
            print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")

    def load_database(self):
        try:
            self.database_metadata.reflect(bind=self.database_engine)
        except SQLAlchemyError as error:
            print(f"Ошибка при загрузке структуры базы данных: {error}")
        if not self.database_metadata.tables:
            print("Таблицы отсутствуют в базе данных. Проверьте базу данных.")
            return
        for table_name in self.database_metadata.tables:
            table = self.database_metadata.tables[table_name]
            self.tables_information[table_name] = {
                'columns': {column.name: str(column.type) for column in table.columns},
                'primary_keys': [column.name for column in table.primary_key],
                'foreign_keys': {foreign_key.column.name: str(foreign_key.target_fullname) for foreign_key in table.foreign_keys}
            }
        print("\n=== База данных загружена. Доступные таблицы ===")
        print(list(self.tables_information.keys()))
        print("===============================================\n")

    def generate_sql(self, query):
        db_structure = {
            "tables": [
                {
                    "table_name": name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }
                for name, info in self.tables_information.items()
            ]
        }
        db_structure_json = json.dumps(db_structure, ensure_ascii=False, indent=2)
        prompt = (
            "You are an expert SQL developer specializing in SQLite databases. "
            "Your task is to generate correct SQL queries based on the provided database structure in response to user queries.\n\n"
            "Here is the structure of the database:\n"
            f"<database_structure>\n"
            f"{db_structure_json}\n"
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
            "max_tokens": 400,
            "temperature": 0
        }
        try:
            model_response = self.chatgpt_request(prompt, maximum_tokens=400, temperature=0)
            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|<generated_sql>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
                '',
                model_response
            ).strip()
            model_response = re.sub(
                r'<generated_sql>',
                '',
                model_response
            ).strip()
            model_response = re.sub(r'\bQuery\b', '', model_response, flags=re.IGNORECASE).strip()
            model_response = re.sub(r'Ответ:', '', model_response, flags=re.IGNORECASE).strip()
            model_response = re.sub(r'<sql_query>', '', model_response, flags=re.IGNORECASE).strip()
            if "Ответ завершен" in model_response:
                model_response = model_response.split("Ответ завершен")[0]
            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")
            sql_queries = []
            current_query = ""
            for line in model_response.splitlines():
                line = line.strip()
                line = re.sub(r'--.*$', '', line).strip()
                if not line or "Your Answer:" in line or "Ответ завершен." in line:
                    continue
                if re.match(r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)', line, re.IGNORECASE):
                    if current_query:
                        current_query += " " + line
                    else:
                        current_query = line
                else:
                    current_query += " " + line
                if current_query.endswith(';'):
                    sql_queries.append(current_query.strip())
                    current_query = ""
            sql_queries = [sql for sql in sql_queries if sql]
            unique_sql_queries = list(set(sql_queries))
            if unique_sql_queries:
                print("\n=== Сгенерированные SQL-запросы ===")
                for index, sql in enumerate(unique_sql_queries, 1):
                    print(f"{index}. {sql.strip(';')}")
                print("==============================\n")
                return unique_sql_queries
            else:
                print("Не удалось найти корректные SQL-запросы в ответе модели.")
                return None
        except requests.exceptions.RequestException as error:
            print(f"Произошла ошибка при запросе: {error}")
            return None


    def generate_info(self, query):
        if not self.tables_information:
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
                for name, info in self.tables_information.items()
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
            model_response = self.chatgpt_request(prompt, maximum_tokens=600, temperature=0)
            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
                '',
                model_response
            ).strip()
            model_response = model_response.split("Ответ завершен")[0]
            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

        except requests.exceptions.RequestException as error:
            print(f"Произошла ошибка при запросе: {error}")
            return None

    def analyze_sql_result(self, sql_result, query):
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
            "В конце ответа напиши 'Ответ завершен.'"
        )

        payload = {
            "prompt": prompt,
            "max_tokens": 200,
            "temperature": 0
        }

        try:
            analysis = self.chatgpt_request(prompt, maximum_tokens=200, temperature=0)
            return analysis

        except requests.exceptions.RequestException as error:
            print(f"Ошибка при запросе: {error}")
            return None


    def clean_ai_response(self, response_text):
        cleaned_text = re.sub(r'<\|.*?\|>', '', response_text)
        cleaned_text = re.sub(
            r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
            '',
            cleaned_text
        )

        cleaned_text = re.sub(
            r'Query',
            '', cleaned_text)
        cleaned_text = "\n".join([line.strip() for line in cleaned_text.splitlines() if line.strip()])
        cleaned_text = cleaned_text.split("Ответ завершен")[0]
        return cleaned_text

    def narrow_query_analyzer(self, query):
        sql_queries = self.generate_sql(query)
        if not sql_queries:
            print("Не удалось сгенерировать SQL-запрос.")
            return None

        with self.database_engine.connect() as connection:
            try:
                for sql_query in sql_queries:
                    result = connection.execute(sa.text(sql_query))
                    if result.returns_rows:
                        rows = result.fetchall()
                        analysis = self.analyze_sql_result(rows, query)
                    else:
                        analysis = self.analyze_sql_result([], query)
                    cleaned_analysis = self.clean_ai_response(analysis)
                    if cleaned_analysis:
                        print(f"\nОтвет на ваш запрос: {cleaned_analysis}")
                    else:
                        print("Не удалось получить ответ от ИИ.")
            except SQLAlchemyError as error:
                print(f"Ошибка выполнения SQL-запроса: {error}")



    def execute_sql_queries(self, queries):
        with self.database_engine.connect() as connection:
            inspector = inspect(self.database_engine)
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
                            connection.commit()
                            print("Запрос выполнен успешно!")
                except SQLAlchemyError as error:
                    print(f"Ошибка выполнения запроса: {error}")
        print("Выполнение запросов завершено.")

    def display_tables_info(self):
        if not self.tables_information:
            print("Таблицы отсутствуют в базе данных.")
            return

        print("\n" + "=" * 50)
        print("Информация о таблицах в базе данных:")
        print("=" * 50)

        for table_name, info in self.tables_information.items():
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



if __name__ == '__main__':
    database_url = 'sqlite:///chinook.db'
    openai_api_key = "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"
    proxy_host = "45.147.101.43"
    proxy_port = 8000
    proxy_username = "g0VNyj"
    proxy_password = "qXzRs5"

    try:
        sql_agent = SQLAgent(database_url, openai_api_key, proxy_host, proxy_port, proxy_username, proxy_password)
        print("Подключение к базе данных успешно.")
    except Exception as error:
        print(f"Ошибка подключения к базе данных: {error}")
        exit(1)

    while True:
        try:
            sql_agent = SQLAgent(database_url, openai_api_key, proxy_host, proxy_port, proxy_username, proxy_password)
            sql_agent.display_tables_info()

            user_query = input("Введите ваш запрос (или напишите 'exit' для выхода): ").strip().lower()

            if user_query == 'exit':
                print("Завершение программы.")
                break

            if 'диаграмм' in user_query:
                sql_agent.analyze_query_for_relationships(user_query)
            else:
                query_type = sql_agent.classify_query(user_query)

                if 'sql_generation' in query_type:
                    print("Classification: Генерация SQL запроса")
                    sql_queries = sql_agent.generate_sql(user_query)

                    if sql_queries:
                        sql_agent.execute_sql_queries(sql_queries)
                    else:
                        print("Не удалось сгенерировать SQL-запрос.")

                elif 'general_db_info' in query_type:
                    print("Classification: Общий вопрос")
                    sql_agent.generate_info(user_query)
                elif 'narrow_query' in query_type:
                    print("Classification: узконаправленный запрос")
                    sql_agent.narrow_query_analyzer(user_query)


                else:
                    print("Не удалось классифицировать запрос.")

        except Exception as error:
            print(f"Произошла ошибка: {error}")


        print("==============================")
        if input("Напишите 'exit', чтобы выйти, или нажмите Enter для продолжения... ").strip().lower() == "exit":
            break
        print("==============================")

    print("Программа завершена.")