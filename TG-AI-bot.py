import json
import pydot
from subprocess import run
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer
import graphviz
from subprocess import run
from PIL import Image


import requests
import re
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy_schemadisplay import create_schema_graph
from sqlalchemy.orm import configure_mappers
from PIL import Image


class SQLAgent:
    def __init__(self, db_url, api_url="http://127.0.0.1:1234"):
        self.engine = sa.create_engine(db_url)
        self.metadata = sa.MetaData()
        self.tables_info = {}
        self.api_url = api_url
        self.load_database()

    def classify_query(self, query):
        """Отправляет запрос к модели API для классификации вопроса."""
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

        payload = {
            "prompt": prompt,
            "max_tokens": 20,
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            classification = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Clean up the classification response
            classification = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
    '', classification).strip()

            print(f"Classification: {classification}")  # Add this line to help with debugging
            return classification

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def analyze_query_for_relationships(self, query):
        """
        Анализирует запрос пользователя и возвращает список таблиц и связей,
        которые могут быть использованы в ER-диаграмме.
        """
        # Структура базы данных
        db_structure = {
            "tables": [
                {
                    "table_name": name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }
                for name, info in self.tables_info.items()
            ]
        }

        # Преобразование в JSON строку
        db_structure_json = json.dumps(db_structure, ensure_ascii=False, indent=2)

        # Подготовка промпта для AI модели
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

        # Подготовка данных для API запроса
        payload = {
            "prompt": prompt,
            "max_tokens": 2000,
            "temperature": 0
        }

        try:
            # Вызов ИИ модели через API
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Убираем лишние символы перед JSON и гарантируем, что начинаем с {
            model_response = re.sub(r'^.*?({)', r'\1', model_response, flags=re.DOTALL).strip()

            # Удаляем все лишние символы после завершения JSON
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

            # Если нет данных для построения диаграммы
            if not self.metadata.tables:
                print("Нет данных для создания диаграммы. Загрузите базу данных.")
                return

            # Настраиваем маппинг SQLAlchemy
            configure_mappers()

            try:
                # Генерация ER-диаграммы на основе анализа запроса
                self.generate_er_diagram(tables_and_relationships)

            except ImportError as e:
                print("Необходимо установить pygraphviz для генерации диаграмм.")
                print(f"Ошибка: {e}")
            except Exception as e:
                print(f"Ошибка при создании ER-диаграммы: {e}")

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def generate_er_diagram(self, tables_and_relationships, output_file="er_diagram_auto", output_format="png",
                            log=True, relationship_styles=None):
        """
        Генерация ER-диаграммы на основе полученных таблиц и связей.
        """
        print("Результат анализа запроса:")
        print(tables_and_relationships)

        relevant_tables = [t["table_name"] for t in tables_and_relationships.get("relevant_tables", [])]
        relationships = tables_and_relationships.get("relationships", [])

        # Создаем новый объект MetaData для релевантных таблиц
        relevant_metadata = MetaData()

        # Добавляем только указанные таблицы в новый объект MetaData
        for table_info in tables_and_relationships["relevant_tables"]:
            table_name = table_info["table_name"]
            if table_name in self.metadata.tables:
                print(f"Добавление таблицы: {table_name}")
                Table(table_name, relevant_metadata, autoload_with=self.engine)

        print("Таблицы в relevant_metadata после добавления:", relevant_metadata.tables.keys())

        # Создаем граф ER-диаграммы с помощью graphviz
        try:
            print("Создание графа ER-диаграммы...")
            graph = graphviz.Digraph('ER Diagram', format=output_format)
            graph.attr(rankdir='LR', concentrate='true', size="10,10!", dpi="300", nodesep="1.0", ranksep="1.5")
        except Exception as e:
            print(f"Ошибка при создании ER-диаграммы: {str(e)}")
            return

        # Опциональная настройка стилей связей
        if relationship_styles is None:
            relationship_styles = {
                'one-to-many': {"style": "solid", "color": "black"},
                'many-to-many': {"style": "dashed", "color": "green"},
                'possible': {"style": "dotted", "color": "blue"},
            }

        # Добавляем таблицы как узлы с нужной стилизацией
        for table in relevant_tables:
            print(f"Добавление узла для таблицы: {table}")

            # Формируем структуру таблицы: название таблицы (по центру), пустая строка, столбцы с типами данных
            columns = [
                f"- {col['name']} : {col['data_type'].upper()}"
                for col in tables_and_relationships['relevant_tables'][relevant_tables.index(table)]['columns']
            ]
            table_label = f"{{ {table} | {{ | {' | '.join(columns)} }} }}"

            # Добавляем таблицу как узел графа
            graph.node(table, label=table_label, shape="record", style="filled", color="lightblue",
                       fontname="Helvetica", fontsize="12")

        # Логирование всех таблиц в metadata
        print("Таблицы в метаданных:")
        print(self.metadata.tables.keys())

        # Добавляем все связи, включая "возможные"
        for relationship in relationships:
            table1 = relationship['table1']
            table2 = relationship['table2']

            print(f"Обработка связи: {table1} -> {table2}")

            # Добавляем только связи между релевантными таблицами
            if table1 in relevant_tables and table2 in relevant_tables:
                table1_column = relationship['joining_columns']['table1_column']
                table2_column = relationship['joining_columns']['table2_column']
                label = f"{table1}.{table1_column} -> {table2}.{table2_column}"

                # Определяем тип связи
                relationship_type = relationship.get('relationship_type', 'one-to-many')
                style = relationship_styles.get(relationship_type, {"style": "solid", "color": "black"})

                print(f"Добавление связи: {label}")
                graph.edge(f"{table1}:{table1_column}", f"{table2}:{table2_column}", label=label, style=style["style"],
                           color=style["color"])
            else:
                print(f"Пропуск связи между {table1} и {table2}, так как они не релевантны.")

        print("Релевантные таблицы:")
        print(relevant_tables)

        print("Релевантные связи:")
        for relationship in relationships:
            print(f"{relationship['table1']} -> {relationship['table2']} (колонки: {relationship['joining_columns']})")

        # Экспортируем диаграмму
        dot_file = f"{output_file}.dot"
        graph.save(dot_file)
        print(f"ER-диаграмма сохранена в формате .dot: {dot_file}")

        # Конвертируем .dot файл в нужный формат (например, PNG)
        output_file_with_extension = f"{output_file}.{output_format}"
        graph.render(filename=output_file_with_extension, cleanup=True)

        print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")

        # Открываем изображение для отображения
        img_display = Image.open(f"{output_file}.{output_format}.{output_format}")
        img_display.show()

        if log:
            print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")

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

        db_structure = {
            "tables": [
                {
                    "table_name": name,
                    "columns": list(info['columns'].keys()),
                    "primary_keys": info['primary_keys'],
                    "foreign_keys": list(info['foreign_keys'].keys())
                }
                for name, info in self.tables_info.items()
            ]
        }

        # Преобразование в JSON строку
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
            "max_tokens": 400,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

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

            # Обрезаем текст после слов "Ответ завершен."
            if "Ответ завершен" in model_response:
                model_response = model_response.split("Ответ завершен")[0] + "Ответ завершен."

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

            sql_queries = []
            current_query = ""

            # Обработка ответа модели, включая многострочные запросы
            for line in model_response.splitlines():
                line = line.strip()
                # Удаляем однострочные комментарии
                line = re.sub(r'--.*$', '', line).strip()
                if not line or "Your Answer:" in line or "Ответ завершен." in line:
                    continue

                # Проверяем на корректный SQL-запрос
                if re.match(r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)', line, re.IGNORECASE):
                    if current_query:
                        current_query += " " + line
                    else:
                        current_query = line
                else:
                    current_query += " " + line

                # Проверка на завершение запроса
                if current_query.endswith(';'):
                    sql_queries.append(current_query.strip())
                    current_query = ""

            # Исключение пустых строк и некорректных SQL-запросов
            sql_queries = [sql for sql in sql_queries if sql]

            # Удаление дубликатов запросов
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


    def generate_info(self, query):
        """Отправляет запрос к модели API для генерации и выводит информацию."""
        if not self.tables_info:
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
                for name, info in self.tables_info.items()
            ]
        }

        # Преобразование в JSON строку
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
            "max_tokens": 600,  # Увеличил количество токенов для ответа
            "temperature": 0
        }

        try:
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            model_response = response.json().get('choices', [{}])[0].get('text', '').strip()

            # Улучшенная фильтрация ненужного текста
            model_response = re.sub(
                r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
    '',
                model_response
            ).strip()

            # Обрезаем текст после слов "Ответ завершен."
            model_response = model_response.split("Ответ завершен")[0] + "Ответ завершен."

            print("\n=== Ответ модели ===")
            print(model_response)
            print("====================\n")

        except requests.exceptions.RequestException as e:
            print(f"Произошла ошибка при запросе: {e}")
            return None

    def analyze_sql_result(self, sql_result, query):
        """Отправляет результат SQL-запроса в ИИ для анализа и получения окончательного ответа."""
        if not sql_result:  # Обработка пустого результата
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
            response = requests.post(f"{self.api_url}/v1/completions", json=payload)
            response.raise_for_status()
            analysis = response.json().get('choices', [{}])[0].get('text', '').strip()
            return analysis

        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе: {e}")
            return None

    def clean_ai_response(self, response_text):
        """Очищает вывод ИИ от ненужных символов и текстовых артефактов."""
        # Убираем все технические теги, вроде <|end_of_text|> и подобных
        cleaned_text = re.sub(r'<\|.*?\|>', '', response_text)

        # Убираем лишние символы вроде URL-подобных строк
        cleaned_text = re.sub(r'<\|.*?\|>|```sql|://|<!--.*?-->|//.*|/\*.*?\*/|<!\[endif.*?\]|после вывода запроса\.|после вывода SQL-запроса\.|SQL:|<sql_query>\.|###\.|SQL\.|Query:|### SQL|SQL|### <database_structure>|###|<database_structure>',
    '', cleaned_text)

        cleaned_text = re.sub(
            r'Query',
            '', cleaned_text)

        # Удаляем пустые строки и лишние пробелы
        cleaned_text = "\n".join([line.strip() for line in cleaned_text.splitlines() if line.strip()])

        # Обрезаем текст после слов "Ответ завершен."
        cleaned_text = cleaned_text.split("Ответ завершен")[0] + "Ответ завершен."

        return cleaned_text

    def narrow_query_analyzer(self, query):
        """Обрабатывает узконаправленные запросы с выполнением SQL и анализом результата."""
        sql_queries = self.generate_sql(query)

        if not sql_queries:
            print("Не удалось сгенерировать SQL-запрос.")
            return None

        with self.engine.connect() as connection:
            try:
                for sql_query in sql_queries:
                    result = connection.execute(sa.text(sql_query))

                    if result.returns_rows:
                        rows = result.fetchall()

                        # Если данные найдены, отправляем их на анализ
                        analysis = self.analyze_sql_result(rows, query)
                    else:
                        analysis = self.analyze_sql_result([], query)  # Пустой список

                    # Очищаем ответ ИИ — передаем только сам текст
                    cleaned_analysis = self.clean_ai_response(analysis)


                    if cleaned_analysis:  # Проверяем на None
                        print(f"\nОтвет на ваш запрос: {cleaned_analysis}")
                    else:
                        print("Не удалось получить ответ от ИИ.")

            except SQLAlchemyError as e:
                print(f"Ошибка выполнения SQL-запроса: {e}")



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
    try:
        agent = SQLAgent(db_url)
        print("Подключение к базе данных успешно.")
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        exit(1)

    while True:
        try:
            agent = SQLAgent(db_url)
            # Отображение информации о таблицах базы данных
            agent.display_tables_info()

            # Получение запроса от пользователя
            user_query = input("Введите ваш запрос (или напишите 'exit' для выхода): ").strip().lower()

            # Выход, если пользователь вводит 'exit'
            if user_query == 'exit':
                print("Завершение программы.")
                break

            # Обработка запросов, связанных с диаграммами
            if 'диаграмм' in user_query:
                agent.analyze_query_for_relationships(user_query)  # Генерация ER-диаграммы
            else:
                query_type = agent.classify_query(user_query)

                # Обработка SQL-запросов
                if 'sql_generation' in query_type:
                    print("Classification: Генерация SQL запроса")
                    sql_queries = agent.generate_sql(user_query)

                    if sql_queries:
                        agent.execute_sql_queries(sql_queries)
                    else:
                        print("Не удалось сгенерировать SQL-запрос.")

                # Обработка запросов, связанных с общей информацией о базе данных
                elif 'general_db_info' in query_type:
                    print("Classification: Общий вопрос")
                    agent.generate_info(user_query)
                elif 'narrow_query' in query_type:
                    print("Classification: узконаправленный запрос")
                    agent.narrow_query_analyzer(user_query)


                # Обработка неклассифицированных запросов
                else:
                    print("Не удалось классифицировать запрос.")

        except Exception as e:
            print(f"Произошла ошибка: {e}")

        # Запрос на продолжение или выход
        print("==============================")
        if input("Напишите 'exit', чтобы выйти, или нажмите Enter для продолжения... ").strip().lower() == "exit":
            break
        print("==============================")

    print("Программа завершена.")
