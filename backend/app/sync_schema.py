"""
Script to compare SQLAlchemy models with the current PostgreSQL schema, print SQL for missing columns/tables, and execute the changes automatically.
"""

import asyncio
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable
from app.models import Base
from app.database import engine

def sync_schema_sync(conn):
    inspector = inspect(conn)
    metadata = Base.metadata
    model_tables = {table.name: table for table in metadata.sorted_tables}
    db_tables = inspector.get_table_names()
    for table_name, table in model_tables.items():
        if table_name not in db_tables:
            print(f"-- Table missing: {table_name}")
            create_sql = str(CreateTable(table).compile(conn))
            print(create_sql)
            conn.execute(text(create_sql))
            continue
        db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in db_columns:
                print(f"-- Column missing in {table_name}: {col.name} ({col.type})")
                alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col.type}'
                print(alter_sql)
                conn.execute(text(alter_sql))
    print("Schema sync complete.")

async def sync_schema():
    async with engine.begin() as conn:
        await conn.run_sync(sync_schema_sync)

if __name__ == "__main__":
    asyncio.run(sync_schema())
