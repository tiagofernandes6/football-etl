import os
import duckdb
import pandas as pd
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class DatabaseManager:
    """
    Gere a ligação ao DuckDB e operações de leitura/escrita
    nas camadas bronze, silver e gold.
    """

    DB_PATH = os.getenv("DUCKDB_PATH", "./data/football.duckdb")

    def __init__(self):
        os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
        self.conn = duckdb.connect(self.DB_PATH)
        self._init_schemas()

    def _init_schemas(self):
        """Cria os schemas bronze, silver e gold se não existirem."""
        for schema in ["bronze", "silver", "gold"]:
            self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        logger.debug("Schemas inicializados: bronze, silver, gold")

    def insert_bronze(self, table_name: str, rows: list[dict]):
        """
        Insere dados raw na camada bronze.
        Cada linha tem: ingested_at, league_name, league_id, season, raw_json
        """
        if not rows:
            logger.warning(f"Nenhum dado para inserir em bronze.{table_name}")
            return

        df = pd.DataFrame(rows)

        # Cria a tabela se não existir e insere
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS bronze.{table_name} (
                ingested_at  TIMESTAMP,
                league_name  VARCHAR,
                league_id    INTEGER,
                season       INTEGER,
                raw_json     JSON
            )
        """)

        self.conn.execute(
            f"INSERT INTO bronze.{table_name} SELECT * FROM df"
        )
        logger.info(f"Inseridos {len(rows)} registos em bronze.{table_name}")

    def query(self, sql: str) -> pd.DataFrame:
        """Executa uma query e devolve um DataFrame."""
        return self.conn.execute(sql).df()

    def close(self):
        self.conn.close()
