import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from db_agent import SQLAgent
from query_classifier import QueryClassifier
from sql_generator import SQLGenerator
from info_generator import InfoGenerator
from sql_executor import SQLExecutor
from narrow_query_analyzer import NarrowQueryAnalyzer
from er_diagram_generator import ERDiagramGenerator
from relationship_analyzer import RelationshipAnalyzer


if __name__ == '__main__':
    db_url = 'sqlite:///chinook.db'
    api_url = "http://127.0.0.1:1234"  #  URL вашего API

    try:
        engine = sa.create_engine(db_url)
        metadata = sa.MetaData()
        metadata.reflect(bind=engine)
        print("Подключение к базе данных успешно.")
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        exit(1)


    agent = SQLAgent(db_url, api_url)
    query_classifier = QueryClassifier(api_url)
    sql_generator = SQLGenerator(api_url)
    info_generator = InfoGenerator(api_url)
    sql_executor = SQLExecutor(agent.engine)
    narrow_query_analyzer = NarrowQueryAnalyzer(api_url)
    er_diagram_generator = ERDiagramGenerator(agent.engine, agent.metadata)
    relationship_analyzer = RelationshipAnalyzer(api_url)

    while True:
        try:
            agent.display_tables_info()

            user_query = input("Введите ваш запрос (или напишите 'exit' для выхода): ").strip().lower()

            if user_query == 'exit':
                print("Завершение программы.")
                break

            if 'диаграмм' in user_query:
                tables_and_relationships = relationship_analyzer.analyze(user_query, agent.tables_info)
                if tables_and_relationships:
                    er_diagram_generator.generate(tables_and_relationships)
                else:
                    print("Не удалось проанализировать диаграммы.")
            else:
                query_type = query_classifier.classify(user_query)
                print(f"Тип запроса: {query_type}")

                if 'sql_generation' in query_type:
                    sql_queries = sql_generator.generate(user_query, agent.tables_info)
                    if sql_queries:
                        print("Сгенерированные SQL-запросы:")
                        for query in sql_queries:
                            print(query)
                        sql_executor.execute(sql_queries)
                    else:
                        print("Не удалось сгенерировать SQL-запрос.")

                elif 'general_db_info' in query_type:
                    info = info_generator.generate(user_query, agent.tables_info)
                    if info:
                        print("Информация о базе данных:")
                        print(info)
                    else:
                        print("Не удалось получить информацию о базе данных.")

                elif 'narrow_query' in query_type:
                    sql_queries = sql_generator.generate(user_query, agent.tables_info)
                    if sql_queries:
                        with agent.engine.connect() as connection:
                            analysis_results = []
                            for sql_query in sql_queries:
                                result = connection.execute(sa.text(sql_query))
                                rows = result.fetchall() if result.returns_rows else []
                                analysis = narrow_query_analyzer.analyze(user_query, rows)
                                analysis_results.append(analysis)

                            if analysis_results:
                                print("Результаты анализа узконаправленного запроса:")
                                for analysis in analysis_results:
                                    print(analysis)
                            else:
                                print("Анализ не дал результатов.")
                    else:
                        print("Не удалось сгенерировать SQL-запрос для узконаправленного запроса.")

                else:
                    print("Не удалось классифицировать запрос.")

        except Exception as e:
            print(f"Произошла ошибка: {e}")

        if input("Напишите 'exit', чтобы выйти, или нажмите Enter для продолжения... ").strip().lower() == "exit":
            break
