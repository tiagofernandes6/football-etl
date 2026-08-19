FROM apache/airflow:2.8.0-python3.11

USER airflow

RUN pip install --no-cache-dir \
    duckdb==1.5.3 \
    dbt-core==1.8.0 \
    dbt-duckdb==1.8.0 \
    requests==2.31.0 \
    python-dotenv==1.0.0 \
    loguru==0.7.3 \
    pandas==2.2.0
