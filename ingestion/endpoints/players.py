import json
from datetime import datetime
from loguru import logger
from ingestion.client import FootballAPIClient
from storage.database import DatabaseManager


def ingest_top_scorers(league_name: str, league_id: int, season: int):
    """
    Ingere os melhores marcadores de uma liga/temporada e guarda em bronze.
    """
    client = FootballAPIClient()
    db = DatabaseManager()

    logger.info(f"A ingerir marcadores: {league_name} | temporada {season}")
    raw_data = client.get_top_scorers(league_id, season)

    players = raw_data.get("response", [])
    logger.info(f"{len(players)} jogadores encontrados")

    rows = []
    for item in players:
        rows.append({
            "ingested_at": datetime.utcnow().isoformat(),
            "league_name": league_name,
            "league_id": league_id,
            "season": season,
            "raw_json": json.dumps(item),
        })

    db.insert_bronze("raw_top_scorers", rows)
    logger.success(f"Marcadores guardados em bronze: {len(rows)} registos")


def ingest_all_top_scorers(season: int, current_season: int = 2024):
    """Ingere marcadores para todas as ligas configuradas.
    Épocas históricas (< current_season) são saltadas se já existirem na bronze."""
    client = FootballAPIClient()
    db = DatabaseManager()
    for league_name, league_id in client.LEAGUES.items():
        if season < current_season and db.has_data("raw_top_scorers", league_name, season):
            logger.info(f"Dados já existem para {league_name} {season} — a saltar")
            continue
        ingest_top_scorers(league_name, league_id, season)
    db.close()
