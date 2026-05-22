-- gold/team_performance.sql
-- Agrega estatísticas por equipa e liga para análise final

WITH fixtures AS (
    SELECT * FROM {{ ref('stg_fixtures') }}
),

standings AS (
    SELECT * FROM {{ ref('stg_standings') }}
),

-- Calcula médias de golos por jogo para cada equipa
home_stats AS (
    SELECT
        league_name,
        season,
        home_team_id    AS team_id,
        home_team       AS team_name,
        COUNT(*)        AS home_games,
        SUM(home_goals) AS home_goals_scored,
        SUM(away_goals) AS home_goals_conceded,
        SUM(CASE WHEN result = 'home' THEN 1 ELSE 0 END) AS home_wins
    FROM fixtures
    GROUP BY league_name, season, home_team_id, home_team
),

away_stats AS (
    SELECT
        league_name,
        season,
        away_team_id    AS team_id,
        away_team       AS team_name,
        COUNT(*)        AS away_games,
        SUM(away_goals) AS away_goals_scored,
        SUM(home_goals) AS away_goals_conceded,
        SUM(CASE WHEN result = 'away' THEN 1 ELSE 0 END) AS away_wins
    FROM fixtures
    GROUP BY league_name, season, away_team_id, away_team
),

combined AS (
    SELECT
        COALESCE(h.league_name, a.league_name)  AS league_name,
        COALESCE(h.season, a.season)            AS season,
        COALESCE(h.team_id, a.team_id)          AS team_id,
        COALESCE(h.team_name, a.team_name)      AS team_name,
        COALESCE(h.home_games, 0)               AS home_games,
        COALESCE(a.away_games, 0)               AS away_games,
        COALESCE(h.home_goals_scored, 0) + COALESCE(a.away_goals_scored, 0)     AS total_goals_scored,
        COALESCE(h.home_goals_conceded, 0) + COALESCE(a.away_goals_conceded, 0) AS total_goals_conceded,
        COALESCE(h.home_wins, 0) + COALESCE(a.away_wins, 0)                     AS total_wins
    FROM home_stats h
    FULL OUTER JOIN away_stats a
        ON h.team_id = a.team_id AND h.season = a.season
)

SELECT
    c.*,
    s.position,
    s.points,
    s.goal_difference,
    s.form,
    ROUND(total_goals_scored::FLOAT / NULLIF(home_games + away_games, 0), 2) AS avg_goals_per_game,
    ROUND(total_wins::FLOAT / NULLIF(home_games + away_games, 0) * 100, 1)   AS win_rate_pct
FROM combined c
LEFT JOIN standings s
    ON c.team_id = s.team_id AND c.season = s.season
ORDER BY league_name, position
