-- silver/stg_fixtures.sql
-- Transforma os jogos raw (bronze) em dados limpos e tipados

WITH raw AS (
    SELECT
        raw_json,
        league_name,
        season,
        ingested_at
    FROM {{ source('bronze', 'raw_fixtures') }}
),

parsed AS (
    SELECT
        ingested_at,
        league_name,
        season,

        -- Fixture
        (raw_json->>'$.fixture.id')::INTEGER           AS fixture_id,
        (raw_json->>'$.fixture.date')::TIMESTAMP        AS match_datetime,
        raw_json->>'$.fixture.status.short'             AS status,

        -- Liga
        (raw_json->>'$.league.id')::INTEGER             AS league_id,
        raw_json->>'$.league.name'                      AS league_name_api,
        raw_json->>'$.league.round'                     AS round,

        -- Equipas
        (raw_json->>'$.teams.home.id')::INTEGER         AS home_team_id,
        raw_json->>'$.teams.home.name'                  AS home_team,
        (raw_json->>'$.teams.home.winner')::BOOLEAN     AS home_winner,

        (raw_json->>'$.teams.away.id')::INTEGER         AS away_team_id,
        raw_json->>'$.teams.away.name'                  AS away_team,
        (raw_json->>'$.teams.away.winner')::BOOLEAN     AS away_winner,

        -- Golos
        (raw_json->>'$.goals.home')::INTEGER            AS home_goals,
        (raw_json->>'$.goals.away')::INTEGER            AS away_goals

    FROM raw
)

SELECT
    *,
    CASE
        WHEN home_goals > away_goals  THEN 'home'
        WHEN away_goals > home_goals  THEN 'away'
        WHEN home_goals = away_goals  THEN 'draw'
        ELSE NULL
    END AS result,
    match_datetime::DATE AS match_date
FROM parsed
WHERE status = 'FT'  -- só jogos terminados
