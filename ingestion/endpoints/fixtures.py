import json
from datetime import datetime
from loguru import logger
from ingestion.client import FootballAPIClient
from storage.database import DatabaseManager


def ingest_fixtures(league_name: str, league_id: int, season: int):
    """
    Ingere todos os jogos de uma liga/temporada e guarda em bronze.
    """
    client = FootballAPIClient()
    db = DatabaseManager()

    logger.info(f"A ingerir jogos: {league_name} | temporada {season}")
    raw_data = client.get_fixtures(league_id, season)

    fixtures = raw_data.get("response", [])
    logger.info(f"{len(fixtures)} jogos encontrados")

    rows = []
    for item in fixtures:
        rows.append({
            "ingested_at": datetime.utcnow().isoformat(),
            "league_name": league_name,
            "league_id": league_id,
            "season": season,
            "raw_json": json.dumps(item),  # guardamos o JSON completo no bronze
        })

    db.insert_bronze("raw_fixtures", rows)
    logger.success(f"Jogos guardados em bronze: {len(rows)} registos")


def ingest_all_fixtures(season: int):
    """Ingere jogos para todas as ligas configuradas."""
    client = FootballAPIClient()
    for league_name, league_id in client.LEAGUES.items():
        ingest_fixtures(league_name, league_id, season)
