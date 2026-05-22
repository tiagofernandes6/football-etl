from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Importações do nosso projeto
import sys
sys.path.insert(0, "/opt/airflow/project")

from ingestion.endpoints.fixtures import ingest_all_fixtures
from ingestion.endpoints.standings import ingest_all_standings
from ingestion.endpoints.players import ingest_all_top_scorers

# Temporada atual
SEASON = 2024

default_args = {
    "owner": "football-etl",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="football_pipeline",
    description="Pipeline ETL diário — Premier League e Liga Portugal",
    default_args=default_args,
    start_date=datetime(2024, 8, 1),
    schedule_interval="0 6 * * *",  # Todos os dias às 6h
    catchup=False,
    tags=["football", "etl"],
) as dag:

    # ── INGESTÃO (Bronze) ──────────────────────────────────────────────────
    ingest_fixtures = PythonOperator(
        task_id="ingest_fixtures",
        python_callable=ingest_all_fixtures,
        op_kwargs={"season": SEASON},
    )

    ingest_standings = PythonOperator(
        task_id="ingest_standings",
        python_callable=ingest_all_standings,
        op_kwargs={"season": SEASON},
    )

    ingest_players = PythonOperator(
        task_id="ingest_top_scorers",
        python_callable=ingest_all_top_scorers,
        op_kwargs={"season": SEASON},
    )

    # ── TRANSFORMAÇÃO (Silver → Gold via dbt) ────────────────────────────
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command="cd /opt/airflow/project/dbt_project && dbt run --profiles-dir .",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/project/dbt_project && dbt test --profiles-dir .",
    )

    # ── QUALIDADE DE DADOS ────────────────────────────────────────────────
    validate_quality = BashOperator(
        task_id="validate_quality",
        bash_command="cd /opt/airflow/project && python -m expectations.run_checks",
    )

    # ── ORDEM DE EXECUÇÃO ────────────────────────────────────────────────
    # Ingestões correm em paralelo, depois dbt, depois testes e validação
    [ingest_fixtures, ingest_standings, ingest_players] >> dbt_run >> dbt_test >> validate_quality
