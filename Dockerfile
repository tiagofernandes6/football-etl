FROM apache/airflow:2.8.0-python3.11

USER root

COPY certificados_babel.pem /tmp/certificados_babel.pem

RUN apt-get update && apt-get install -y ca-certificates && \
    csplit -z -f /usr/local/share/ca-certificates/babel- \
        /tmp/certificados_babel.pem \
        '/-----BEGIN CERTIFICATE-----/' '{*}' && \
    for f in /usr/local/share/ca-certificates/babel-*; do mv "$f" "$f.crt"; done && \
    update-ca-certificates

USER airflow

RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    duckdb==1.5.3 \
    dbt-core==1.8.0 \
    dbt-duckdb==1.8.0 \
    requests==2.31.0 \
    python-dotenv==1.0.0 \
    loguru==0.7.3 \
    pandas==2.2.0

ENV REQUESTS_CA_BUNDLE=/tmp/certificados_babel.pem
ENV SSL_CERT_FILE=/tmp/certificados_babel.pem
