import os
import requests
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class FootballAPIClient:
    """
    Cliente HTTP para a API-Football (api-sports.io).
    Gere autenticação, rate limiting e erros de forma centralizada.
    """

    BASE_URL = os.getenv("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
    API_KEY = os.getenv("API_FOOTBALL_KEY")

    # IDs das ligas que queremos ingerir
    LEAGUES = {
        "premier_league": 39,
        "liga_portugal": 94,
    }

    def __init__(self):
        if not self.API_KEY:
            raise ValueError("API_FOOTBALL_KEY não está definida no ficheiro .env")

        self.session = requests.Session()
        self.session.headers.update({
            "x-apisports-key": self.API_KEY,
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Faz um GET request e trata erros de forma centralizada."""
        url = f"{self.BASE_URL}/{endpoint}"
        logger.info(f"GET {url} | params={params}")

        response = self.session.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        # A API-Football devolve erros dentro do JSON
        if data.get("errors"):
            raise ValueError(f"Erro da API: {data['errors']}")

        remaining = response.headers.get("x-ratelimit-requests-remaining", "?")
        logger.info(f"Requests restantes hoje: {remaining}")

        return data

    def get_standings(self, league_id: int, season: int) -> dict:
        """Classificação de uma liga numa temporada."""
        return self._get("standings", params={"league": league_id, "season": season})

    def get_fixtures(self, league_id: int, season: int) -> dict:
        """Todos os jogos de uma liga numa temporada."""
        return self._get("fixtures", params={"league": league_id, "season": season})

    def get_top_scorers(self, league_id: int, season: int) -> dict:
        """Melhores marcadores de uma liga numa temporada."""
        return self._get("players/topscorers", params={"league": league_id, "season": season})
