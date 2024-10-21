import graphviz
from PIL import Image
from sqlalchemy.orm import configure_mappers
import json
import sqlalchemy as sa

class ERDiagramGenerator:

    def __init__(self, engine, metadata):
        self.engine = engine
        self.metadata = metadata


    def generate(self, tables_and_relationships, output_file="er_diagram_auto", output_format="png",
                            log=True, relationship_styles=None):

        print("Результат анализа запроса:")
        print(tables_and_relationships)

        relevant_tables = [t["table_name"] for t in tables_and_relationships.get("relevant_tables", [])]
        relationships = tables_and_relationships.get("relationships", [])


        relevant_metadata = sa.MetaData()


        for table_info in tables_and_relationships["relevant_tables"]:
            table_name = table_info["table_name"]
            if table_name in self.metadata.tables:
                print(f"Добавление таблицы: {table_name}")
                sa.Table(table_name, relevant_metadata, autoload_with=self.engine)

        print("Таблицы в relevant_metadata после добавления:", relevant_metadata.tables.keys())


        try:
            print("Создание графа ER-диаграммы...")
            graph = graphviz.Digraph('ER Diagram', format=output_format)
            graph.attr(rankdir='LR', concentrate='true', size="10,10!", dpi="300", nodesep="1.0", ranksep="1.5")
        except Exception as e:
            print(f"Ошибка при создании ER-диаграммы: {str(e)}")
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
                f"- {col['name']} : {col['data_type'].upper()}"
                for col in tables_and_relationships['relevant_tables'][relevant_tables.index(table)]['columns']
            ]
            table_label = f"{{ {table} | {{ | {' | '.join(columns)} }} }}"


            graph.node(table, label=table_label, shape="record", style="filled", color="lightblue",
                       fontname="Helvetica", fontsize="12")


        print("Таблицы в метаданных:")
        print(self.metadata.tables.keys())


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
                graph.edge(f"{table1}:{table1_column}", f"{table2}:{table2_column}", label=label, style=style["style"],
                           color=style["color"])
            else:
                print(f"Пропуск связи между {table1} и {table2}, так как они не релевантны.")

        print("Релевантные таблицы:")
        print(relevant_tables)

        print("Релевантные связи:")
        for relationship in relationships:
            print(f"{relationship['table1']} -> {relationship['table2']} (колонки: {relationship['joining_columns']})")


        dot_file = f"{output_file}.dot"
        graph.save(dot_file)
        print(f"ER-диаграмма сохранена в формате .dot: {dot_file}")


        output_file_with_extension = f"{output_file}.{output_format}"
        graph.render(filename=output_file_with_extension, cleanup=True)

        print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")


        img_display = Image.open(f"{output_file}.{output_format}.{output_format}")
        img_display.show()

        if log:
            print(f"ER-диаграмма успешно создана и сохранена в файл: {output_file_with_extension}")