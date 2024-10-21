import json
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers
from PIL import Image
import requests
import re
import graphviz


class SQLAgent:
    def __init__(self, db_url, api_url="http://127.0.0.1:1234"):
        self.engine = sa.create_engine(db_url)
        self.metadata = sa.MetaData()
        self.tables_info = {}
        self.api_url = api_url
        self.load_database()

    def load_database(self):
        try:
            self.metadata.reflect(bind=self.engine)
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

    def display_tables_info(self):
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