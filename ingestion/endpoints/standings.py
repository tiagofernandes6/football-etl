import json
from datetime import datetime
from loguru import logger
from ingestion.client import FootballAPIClient
from storage.database import DatabaseManager


def ingest_standings(league_name: str, league_id: int, season: int):
    """
    Ingere a classificação de uma liga/temporada e guarda em bronze.
    """
    client = FootballAPIClient()
    db = DatabaseManager()

    logger.info(f"A ingerir classificação: {league_name} | temporada {season}")
    raw_data = client.get_standings(league_id, season)

    standings = raw_data.get("response", [])
    logger.info(f"{len(standings)} registos encontrados")

    rows = []
    for item in standings:
        rows.append({
            "ingested_at": datetime.utcnow().isoformat(),
            "league_name": league_name,
            "league_id": league_id,
            "season": season,
            "raw_json": json.dumps(item),
        })

    db.insert_bronze("raw_standings", rows)
    logger.success(f"Classificação guardada em bronze: {len(rows)} registos")


def ingest_all_standings(season: int):
    """Ingere classificação para todas as ligas configuradas."""
    client = FootballAPIClient()
    for league_name, league_id in client.LEAGUES.items():
        ingest_standings(league_name, league_id, season)
