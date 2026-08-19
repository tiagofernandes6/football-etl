# ⚽ Football ETL Pipeline

Pipeline de dados para ingestão e análise da **Premier League** e **Liga Portugal**, usando dados da [API-Football](https://www.api-football.com/).

## 🏗️ Arquitetura

```
API-Football → Bronze (raw JSON) → Silver (limpo) → Gold (agregado) → Streamlit
                    └─────────── Airflow orquestra ──────────────┘
                                      └── validações de qualidade
```

## 🛠️ Stack

| Camada | Tecnologia |
|---|---|
| Ingestão | Python + Requests |
| Armazenamento | DuckDB |
| Transformação | dbt |
| Orquestração | Apache Airflow |
| Qualidade | Validações SQL sobre o DuckDB |
| Dashboard | Streamlit + Plotly |
| Ambiente | Docker |

## 🚀 Como correr

### 1. Clonar e configurar

```bash
git clone https://github.com/teu-username/football-etl.git
cd football-etl

cp .env.example .env
# Edita o .env e adiciona a tua API key
```

### 2. Arrancar o Airflow

```bash
docker-compose up airflow-init   # só na primeira vez
docker-compose up -d
```

Acede a **http://localhost:8080** (user: `admin`, pass: `admin`)

### 3. Activar a DAG

No Airflow UI, activa a DAG `football_pipeline` e corre manualmente pela primeira vez.

### 4. Correr localmente (sem Airflow)

```bash
pip install -r requirements.txt

python -c "from ingestion.endpoints.fixtures import ingest_all_fixtures; ingest_all_fixtures(2024)"
cd dbt_project && dbt run --profiles-dir .
python -m expectations.run_checks
```

### 5. Dashboard

```bash
streamlit run app.py
```

Abre em **http://localhost:8501**. Lê o DuckDB indicado por `DUCKDB_PATH`, por isso
precisa que a pipeline tenha corrido pelo menos uma vez.

## 📊 Camadas de dados

### Bronze
Dados raw da API em JSON, sem transformações.

| Tabela | Descrição |
|---|---|
| `raw_fixtures` | Todos os jogos |
| `raw_standings` | Classificações |
| `raw_top_scorers` | Melhores marcadores |

### Silver
Dados limpos, tipados e normalizados.

| Tabela | Descrição |
|---|---|
| `stg_fixtures` | Jogos com golos, equipas, resultado |
| `stg_standings` | Classificação com estatísticas |

### Gold
Dados agregados prontos para análise.

| Tabela | Descrição |
|---|---|
| `team_performance` | Performance completa por equipa |

## 📁 Estrutura

```
football-etl/
├── app.py                   # Dashboard Streamlit
├── dags/                    # DAGs do Airflow
├── ingestion/               # Cliente e endpoints da API
├── storage/                 # Gestão do DuckDB
├── dbt_project/             # Modelos de transformação
│   └── models/
│       ├── bronze/
│       ├── silver/
│       └── gold/
├── expectations/            # Validações de qualidade
├── docker-compose.yml
└── requirements.txt
```

## 🔑 Variáveis de ambiente

```env
API_FOOTBALL_KEY=a_tua_api_key
API_FOOTBALL_BASE_URL=https://v3.football.api-sports.io
DUCKDB_PATH=./data/football.duckdb
```

> ⚠️ Nunca commites o ficheiro `.env` — está no `.gitignore`.
