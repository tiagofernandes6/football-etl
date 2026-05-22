-- silver/stg_standings.sql
-- Transforma a classificação raw em dados limpos e tipados

WITH raw AS (
    SELECT raw_json, league_name, season, ingested_at
    FROM {{ source('bronze', 'raw_standings') }}
),

-- A classificação vem aninhada: response[0].league.standings[0][]
parsed AS (
    SELECT
        ingested_at,
        league_name,
        season,
        (raw_json->>'$.league.id')::INTEGER             AS league_id,
        raw_json->>'$.league.name'                      AS league_name_api,

        -- Iteramos sobre cada equipa na classificação
        unnest(
            from_json(raw_json->>'$.league.standings[0]', '["json"]')
        )                                               AS team_json

    FROM raw
),

flattened AS (
    SELECT
        ingested_at,
        league_name,
        season,
        league_id,
        league_name_api,
        (team_json->>'$.rank')::INTEGER                 AS position,
        (team_json->>'$.team.id')::INTEGER              AS team_id,
        team_json->>'$.team.name'                       AS team_name,
        (team_json->>'$.points')::INTEGER               AS points,
        (team_json->>'$.all.played')::INTEGER           AS played,
        (team_json->>'$.all.win')::INTEGER              AS wins,
        (team_json->>'$.all.draw')::INTEGER             AS draws,
        (team_json->>'$.all.lose')::INTEGER             AS losses,
        (team_json->>'$.all.goals.for')::INTEGER        AS goals_for,
        (team_json->>'$.all.goals.against')::INTEGER    AS goals_against,
        (team_json->>'$.goalsDiff')::INTEGER            AS goal_difference,
        team_json->>'$.form'                            AS form
    FROM parsed
)

SELECT * FROM flattened
