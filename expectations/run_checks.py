import duckdb
import os
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DUCKDB_PATH", "./data/football.duckdb")


def run_checks():
    """
    Corre validações de qualidade de dados em todas as camadas.
    Lança exceção se alguma validação crítica falhar.
    """
    conn = duckdb.connect(DB_PATH)
    failures = []

    logger.info("A iniciar validações de qualidade de dados...")

    checks = [
        # Bronze — dados chegaram?
        {
            "name": "bronze.raw_fixtures tem dados",
            "sql": "SELECT COUNT(*) FROM bronze.raw_fixtures",
            "condition": lambda n: n > 0,
            "critical": True,
        },
        # Silver — sem fixture_id nulo
        {
            "name": "silver.stg_fixtures sem fixture_id nulo",
            "sql": "SELECT COUNT(*) FROM main_silver.stg_fixtures WHERE fixture_id IS NULL",
            "condition": lambda n: n == 0,
            "critical": True,
        },
        # Silver — golos não negativos
        {
            "name": "silver.stg_fixtures golos >= 0",
            "sql": "SELECT COUNT(*) FROM main_silver.stg_fixtures WHERE home_goals < 0 OR away_goals < 0",
            "condition": lambda n: n == 0,
            "critical": True,
        },
        # Silver — fixture_ids únicos
        {
            "name": "silver.stg_fixtures fixture_id único",
            "sql": "SELECT COUNT(*) - COUNT(DISTINCT fixture_id) FROM main_silver.stg_fixtures",
            "condition": lambda n: n == 0,
            "critical": False,
        },
        # Gold — todas as equipas têm pontos
        {
            "name": "gold.team_performance sem pontos nulos",
            "sql": "SELECT COUNT(*) FROM main_gold.team_performance WHERE points IS NULL",
            "condition": lambda n: n == 0,
            "critical": False,
        },
    ]

    for check in checks:
        result = conn.execute(check["sql"]).fetchone()[0]
        passed = check["condition"](result)
        status = "✅" if passed else ("❌ CRÍTICO" if check["critical"] else "⚠️  AVISO")

        logger.info(f"{status} | {check['name']} | resultado: {result}")

        if not passed and check["critical"]:
            failures.append(check["name"])

    conn.close()

    if failures:
        raise ValueError(f"Validações críticas falharam: {failures}")

    logger.success("Todas as validações concluídas com sucesso!")


if __name__ == "__main__":
    run_checks()
