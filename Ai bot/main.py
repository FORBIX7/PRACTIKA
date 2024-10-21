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
                query_type = query_classifier.classify(user_query)

                if 'sql_generation' in query_type:
                    print("Classification: Генерация SQL запроса")
                    sql_queries = sql_generator.generate(user_query, agent.tables_info)
                    if sql_queries:
                        sql_executor.execute(sql_queries)
                    else:
                        print("Не удалось сгенерировать SQL-запрос.")

                elif 'general_db_info' in query_type:
                    print("Classification: Общий вопрос")
                    info_generator.generate(user_query, agent.tables_info)


                elif 'narrow_query' in query_type or 'нarrow_query' in query_type:

                    print("Classification: узконаправленный запрос")

                    sql_queries = sql_generator.generate(user_query, agent.tables_info)

                    if sql_queries:

                        with agent.engine.connect() as connection:

                            try:

                                analysis_results = []  # Список для хранения результатов анализа

                                for sql_query in sql_queries:
                                    result = connection.execute(sa.text(sql_query))

                                    rows = result.fetchall() if result.returns_rows else []

                                    analysis = narrow_query_analyzer.analyze(user_query, rows)

                                    analysis_results.append(analysis)  # Добавляем результат анализа в список

                                if analysis_results:

                                    print("Результаты анализа узконаправленного запроса:")

                                    for analysis in analysis_results:
                                        print(analysis)  # Выводим или обрабатываем результаты анализа

                                else:

                                    print("Анализ не дал результатов.")




                            except SQLAlchemyError as e:

                                print(f"Ошибка выполнения SQL-запроса: {e}")


                    else:

                        print("Не удалось сгенерировать SQL-запрос для узконаправленного запроса.")

                else:
                    print("Не удалось классифицировать запрос.")

        except Exception as e:
            print(f"Произошла ошибка: {e}")


        print("==============================")
        if input("Напишите 'exit', чтобы выйти, или нажмите Enter для продолжения... ").strip().lower() == "exit":
            break
        print("==============================")

    print("Программа завершена.")