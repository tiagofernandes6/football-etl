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


def ingest_all_top_scorers(season: int):
    """Ingere marcadores para todas as ligas configuradas."""
    client = FootballAPIClient()
    for league_name, league_id in client.LEAGUES.items():
        ingest_top_scorers(league_name, league_id, season)
