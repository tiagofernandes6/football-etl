import re
import os
from datetime import date

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Football Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = os.getenv("DUCKDB_PATH", "./data/football.duckdb")

# ── Estilo CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@300;400;500;600&display=swap');

    .main { background-color: #0a0a0a; }
    .stApp { background-color: #0a0a0a; color: #f0f0f0; }

    h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 2px; }

    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        height: 100%;
    }
    .metric-value {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 2.5rem;
        color: #e94560;
        line-height: 1;
    }
    .metric-value-sm {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 1.6rem;
        color: #e94560;
        line-height: 1.1;
    }
    .metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 4px;
    }
    .form-badge {
        display: inline-block;
        width: 24px;
        height: 24px;
        border-radius: 4px;
        text-align: center;
        line-height: 24px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 1px;
    }
    .section-title {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 1.8rem;
        letter-spacing: 3px;
        color: #e94560;
        border-bottom: 2px solid #e94560;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }
    .result-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_round_num(round_str: str) -> int:
    m = re.search(r"\d+$", str(round_str))
    return int(m.group()) if m else 0


def color_form(form) -> str:
    if not form:
        return ""
    colors = {"W": "#27ae60", "D": "#f39c12", "L": "#e74c3c"}
    return "".join(
        f'<span class="form-badge" style="background:{colors.get(c,"#888")};color:white">{c}</span>'
        for c in str(form)
    )


def metric_card(value, label: str, small: bool = False) -> str:
    cls = "metric-value-sm" if small else "metric-value"
    return f"""
    <div class="metric-card">
        <div class="{cls}">{value}</div>
        <div class="metric-label">{label}</div>
    </div>"""


def result_badge(result: str) -> str:
    cfg = {
        "home": ("#27ae60", "Casa"),
        "draw": ("#f39c12", "Empate"),
        "away": ("#e74c3c", "Fora"),
    }
    color, label = cfg.get(result, ("#888", result))
    return f'<span class="result-badge" style="background:{color}">{label}</span>'


PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#f0f0f0", family="Inter"),
    margin=dict(l=0, r=0, t=30, b=0),
)


# ── Dados ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data():
    conn = duckdb.connect(DB_PATH, read_only=True)

    # Deduplica por (team_id, season, league_name) — múltiplas ingestões geram duplicados na bronze
    standings = conn.execute("""
        WITH deduped AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY team_id, season, league_name
                       ORDER BY ingested_at DESC
                   ) AS rn
            FROM main_silver.stg_standings
        )
        SELECT * EXCLUDE (rn) FROM deduped WHERE rn = 1
        ORDER BY season DESC, position
    """).df()

    # Deduplica por fixture_id e recomputa agregações — evita usar gold table inflacionada
    performance = conn.execute("""
        WITH fixtures AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY fixture_id ORDER BY ingested_at DESC) AS rn
            FROM main_silver.stg_fixtures
            WHERE home_goals IS NOT NULL
        ),
        f AS (SELECT * EXCLUDE (rn) FROM fixtures WHERE rn = 1),
        standings AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY team_id, season, league_name
                       ORDER BY ingested_at DESC
                   ) AS rn
            FROM main_silver.stg_standings
        ),
        s AS (SELECT * EXCLUDE (rn) FROM standings WHERE rn = 1),
        home_stats AS (
            SELECT league_name, home_team_id AS team_id, home_team AS team_name,
                   COUNT(*)        AS home_games,
                   SUM(home_goals) AS home_goals_scored,
                   SUM(away_goals) AS home_goals_conceded,
                   SUM(CASE WHEN result = 'home' THEN 1 ELSE 0 END) AS home_wins
            FROM f GROUP BY league_name, home_team_id, home_team
        ),
        away_stats AS (
            SELECT league_name, away_team_id AS team_id, away_team AS team_name,
                   COUNT(*)        AS away_games,
                   SUM(away_goals) AS away_goals_scored,
                   SUM(home_goals) AS away_goals_conceded,
                   SUM(CASE WHEN result = 'away' THEN 1 ELSE 0 END) AS away_wins
            FROM f GROUP BY league_name, away_team_id, away_team
        ),
        combined AS (
            SELECT
                COALESCE(h.league_name, a.league_name)  AS league_name,
                COALESCE(h.team_id, a.team_id)          AS team_id,
                COALESCE(h.team_name, a.team_name)      AS team_name,
                COALESCE(h.home_games, 0)               AS home_games,
                COALESCE(a.away_games, 0)               AS away_games,
                COALESCE(h.home_goals_scored,   0) + COALESCE(a.away_goals_scored,   0) AS total_goals_scored,
                COALESCE(h.home_goals_conceded, 0) + COALESCE(a.away_goals_conceded, 0) AS total_goals_conceded,
                COALESCE(h.home_wins, 0) + COALESCE(a.away_wins, 0) AS total_wins
            FROM home_stats h
            FULL OUTER JOIN away_stats a ON h.team_id = a.team_id
        )
        SELECT c.*,
               st.position, st.points, st.goal_difference, st.form,
               ROUND(total_goals_scored::FLOAT / NULLIF(home_games + away_games, 0), 2) AS avg_goals_per_game,
               ROUND(total_wins::FLOAT        / NULLIF(home_games + away_games, 0) * 100, 1) AS win_rate_pct
        FROM combined c
        LEFT JOIN s st ON c.team_id = st.team_id AND c.league_name = st.league_name
        ORDER BY st.position
    """).df()

    # Deduplica por fixture_id
    fixtures = conn.execute("""
        WITH deduped AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY fixture_id ORDER BY ingested_at DESC) AS rn
            FROM main_silver.stg_fixtures
            WHERE home_goals IS NOT NULL
        )
        SELECT * EXCLUDE (rn) FROM deduped WHERE rn = 1
        ORDER BY match_date
    """).df()

    # Deduplica por (player_id, league_name)
    scorers = conn.execute("""
        WITH ranked AS (
            SELECT
                raw_json->>'$.player.name'                            AS player,
                raw_json->>'$.player.id'                              AS player_id,
                raw_json->>'$.statistics[0].team.name'                AS team,
                (raw_json->>'$.statistics[0].goals.total')::INTEGER   AS goals,
                (raw_json->>'$.statistics[0].games.appearences')::INTEGER AS apps,
                league_name,
                ROW_NUMBER() OVER (
                    PARTITION BY raw_json->>'$.player.id', league_name
                    ORDER BY ingested_at DESC
                ) AS rn
            FROM bronze.raw_top_scorers
        )
        SELECT player, team, goals, apps, league_name
        FROM ranked WHERE rn = 1
        ORDER BY goals DESC
    """).df()

    conn.close()
    return standings, performance, fixtures, scorers


# Carrega e enriquece fixtures com colunas computadas
standings, performance, fixtures, scorers = load_data()
fixtures["round_num"] = fixtures["round"].apply(extract_round_num)
fixtures["total_goals"] = fixtures["home_goals"] + fixtures["away_goals"]
fixtures["match_date"] = pd.to_datetime(fixtures["match_date"])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚽ FOOTBALL\nANALYTICS")
    st.markdown("---")

    leagues = {
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League": "premier_league",
        "🇵🇹 Liga Portugal": "liga_portugal",
    }
    selected_league_label = st.selectbox("Liga", list(leagues.keys()))
    selected_league = leagues[selected_league_label]

    _lf = fixtures[fixtures["league_name"] == selected_league]
    all_teams_sorted = sorted(_lf["home_team"].dropna().unique().tolist())
    min_round = int(_lf["round_num"].min()) if not _lf.empty else 1
    max_round = int(_lf["round_num"].max()) if not _lf.empty else 38

    st.markdown("---")
    st.markdown("### Filtros")

    # Época
    available_seasons = sorted(_lf["season"].dropna().unique().astype(int).tolist(), reverse=True)
    if len(available_seasons) > 1:
        selected_seasons = st.multiselect("Época", available_seasons, default=available_seasons)
        if not selected_seasons:
            selected_seasons = available_seasons
    else:
        selected_seasons = available_seasons

    jornada_range = (
        st.slider("Jornada", min_round, max_round, (min_round, max_round))
        if min_round < max_round
        else (min_round, max_round)
    )

    selected_teams = st.multiselect("Equipa", all_teams_sorted, placeholder="Todas as equipas")

    resultado_opts = {"Vitória casa": "home", "Empate": "draw", "Vitória fora": "away"}
    selected_resultados = st.multiselect("Resultado", list(resultado_opts.keys()), placeholder="Todos")
    selected_resultado_vals = [resultado_opts[r] for r in selected_resultados]

    st.markdown("---")
    st.markdown("**Pipeline**")
    st.markdown("🟢 DuckDB conectado")
    st.markdown(f"📊 {len(_lf)} jogos carregados")


# ── Filtragem global ──────────────────────────────────────────────────────────
league_fixtures_all = fixtures[
    (fixtures["league_name"] == selected_league) & (fixtures["season"].isin(selected_seasons))
].copy()
league_perf = performance[
    (performance["league_name"] == selected_league) & (performance["season"].isin(selected_seasons))
].copy()
league_standings = standings[
    (standings["league_name"] == selected_league) & (standings["season"].isin(selected_seasons))
].copy()
league_scorers = scorers[scorers["league_name"] == selected_league].copy()

# Fixtures filtradas (sidebar: jornada + equipa + resultado)
league_fixtures = league_fixtures_all.copy()
league_fixtures = league_fixtures[
    (league_fixtures["round_num"] >= jornada_range[0])
    & (league_fixtures["round_num"] <= jornada_range[1])
]
if selected_teams:
    league_fixtures = league_fixtures[
        league_fixtures["home_team"].isin(selected_teams)
        | league_fixtures["away_team"].isin(selected_teams)
    ]
if selected_resultado_vals:
    league_fixtures = league_fixtures[league_fixtures["result"].isin(selected_resultado_vals)]


# ── Header ────────────────────────────────────────────────────────────────────
league_name_display = selected_league_label.split(" ", 1)[1]
st.markdown(
    f"<h1 style='font-size:3rem; margin-bottom:0'>{league_name_display}</h1>",
    unsafe_allow_html=True,
)
seasons_label = " · ".join(f"{s}/{str(s+1)[-2:]}" for s in sorted(selected_seasons))
st.markdown(
    f"<p style='color:#888; font-family:Inter; margin-top:0'>{seasons_label} · Dados via API-Football</p>",
    unsafe_allow_html=True,
)

st.markdown("---")


# ── KPIs — Linha 1 (época completa) ──────────────────────────────────────────
total_goals_all = int(
    league_fixtures_all["home_goals"].sum() + league_fixtures_all["away_goals"].sum()
)
avg_goals_all = round(league_fixtures_all["total_goals"].mean(), 2) if not league_fixtures_all.empty else 0
top_scorer = league_scorers.iloc[0]["player"] if not league_scorers.empty else "N/A"
top_goals = int(league_scorers.iloc[0]["goals"]) if not league_scorers.empty else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(metric_card(len(league_fixtures_all), "Jogos disputados"), unsafe_allow_html=True)
with c2:
    st.markdown(metric_card(total_goals_all, "Golos totais"), unsafe_allow_html=True)
with c3:
    st.markdown(metric_card(avg_goals_all, "Média golos/jogo"), unsafe_allow_html=True)
with c4:
    st.markdown(metric_card(top_goals, f"Golos — {top_scorer}"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── KPIs — Linha 2 (novos indicadores) ───────────────────────────────────────
n = len(league_fixtures_all)
home_wins_n = (league_fixtures_all["result"] == "home").sum()
away_wins_n = (league_fixtures_all["result"] == "away").sum()
home_win_pct = round(home_wins_n / n * 100, 1) if n > 0 else 0
away_win_pct = round(away_wins_n / n * 100, 1) if n > 0 else 0

total_cs = int(
    (league_fixtures_all["away_goals"] == 0).sum()
    + (league_fixtures_all["home_goals"] == 0).sum()
)

if not league_fixtures_all.empty:
    tg = league_fixtures_all.nlargest(1, "total_goals").iloc[0]
    top_game_val = int(tg["total_goals"])
    top_game_label = f"{tg['home_team'][:14]} {int(tg['home_goals'])}-{int(tg['away_goals'])} {tg['away_team'][:14]}"
else:
    top_game_val, top_game_label = "N/A", "Jogo mais goleada"

if not league_fixtures_all.empty and league_fixtures_all["round_num"].max() > 0:
    mid_round = league_fixtures_all["round_num"].max() // 2
    avg1 = round(league_fixtures_all[league_fixtures_all["round_num"] <= mid_round]["total_goals"].mean(), 2)
    avg2 = round(league_fixtures_all[league_fixtures_all["round_num"] > mid_round]["total_goals"].mean(), 2)
    volta_val = f"{avg1} → {avg2}"
else:
    volta_val = "N/A"

c5, c6, c7, c8 = st.columns(4)
with c5:
    st.markdown(
        metric_card(f"{home_win_pct}% / {away_win_pct}%", "Vitórias casa / fora", small=True),
        unsafe_allow_html=True,
    )
with c6:
    st.markdown(metric_card(total_cs, "Clean sheets totais"), unsafe_allow_html=True)
with c7:
    st.markdown(metric_card(top_game_val, top_game_label, small=True), unsafe_allow_html=True)
with c8:
    st.markdown(metric_card(volta_val, "Golos/jogo 1ª → 2ª volta", small=True), unsafe_allow_html=True)


# ── Separadores ───────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
tab_class, tab_jogos, tab_marc, tab_equipa, tab_h2h = st.tabs(
    ["📊 Classificação", "⚽ Jogos", "👟 Marcadores", "🏟️ Equipas", "⚔️ Head to Head"]
)


# ── Tab: Classificação ────────────────────────────────────────────────────────
with tab_class:
    if not league_standings.empty:
        st.markdown('<div class="section-title">CLASSIFICAÇÃO</div>', unsafe_allow_html=True)

        disp = league_standings[
            ["position", "team_name", "points", "wins", "draws", "losses",
             "goals_for", "goals_against", "goal_difference", "form"]
        ].copy()
        disp.columns = ["#", "Equipa", "Pts", "V", "E", "D", "GM", "GS", "DG", "Forma"]
        disp["Forma"] = disp["Forma"].apply(color_form)

        n_teams = len(disp)
        cl_spots = 4 if n_teams >= 16 else 2

        def row_style(pos):
            if pos <= cl_spots:
                return "background-color:rgba(39,174,96,0.15)"
            if pos <= cl_spots + 2:
                return "background-color:rgba(52,152,219,0.15)"
            if pos >= n_teams - 2:
                return "background-color:rgba(231,76,60,0.15)"
            return ""

        rows_html = ""
        for _, row in disp.iterrows():
            style = row_style(row["#"])
            cells = "".join(f'<td style="padding:6px 10px">{v}</td>' for v in row)
            rows_html += f'<tr style="{style}">{cells}</tr>'

        header_html = "".join(f'<th style="padding:6px 10px;text-align:left">{c}</th>' for c in disp.columns)
        table_html = f"""
        <table style="width:100%;border-collapse:collapse;font-family:Inter;font-size:0.9rem">
            <thead><tr style="border-bottom:1px solid #333">{header_html}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <div style="margin-top:8px;font-size:0.75rem;color:#888">
            <span style="color:#27ae60">■</span> Champions League &nbsp;
            <span style="color:#3498db">■</span> Europa/Conference &nbsp;
            <span style="color:#e74c3c">■</span> Descida
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-title">PONTOS POR EQUIPA</div>', unsafe_allow_html=True)
        if not league_perf.empty:
            top10 = league_perf.head(10).sort_values("points")
            fig = px.bar(
                top10, x="points", y="team_name", orientation="h",
                color="points", color_continuous_scale=["#1a1a2e", "#e94560"],
                labels={"points": "Pontos", "team_name": ""},
            )
            fig.update_layout(**PLOTLY_BASE, showlegend=False, coloraxis_showscale=False)
            fig.update_xaxes(gridcolor="#222")
            fig.update_yaxes(gridcolor="#222")
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-title">GOLOS MARCADOS VS SOFRIDOS</div>', unsafe_allow_html=True)
        if not league_perf.empty:
            top10 = league_perf.head(10)
            fig2 = go.Figure([
                go.Bar(name="Marcados", x=top10["team_name"], y=top10["total_goals_scored"], marker_color="#e94560"),
                go.Bar(name="Sofridos", x=top10["team_name"], y=top10["total_goals_conceded"], marker_color="#0f3460"),
            ])
            fig2.update_layout(**PLOTLY_BASE, barmode="group", legend=dict(bgcolor="rgba(0,0,0,0)"), xaxis_tickangle=-45)
            fig2.update_xaxes(gridcolor="#222")
            fig2.update_yaxes(gridcolor="#222")
            st.plotly_chart(fig2, use_container_width=True)

    if not league_perf.empty and "win_rate_pct" in league_perf.columns:
        st.markdown('<div class="section-title">TAXA DE VITÓRIAS (%)</div>', unsafe_allow_html=True)
        wr = league_perf.dropna(subset=["win_rate_pct"]).sort_values("win_rate_pct", ascending=False)
        fig_wr = px.bar(
            wr, x="team_name", y="win_rate_pct",
            color="win_rate_pct", color_continuous_scale=["#1a1a2e", "#e94560"],
            labels={"win_rate_pct": "% Vitórias", "team_name": ""},
            text=wr["win_rate_pct"].apply(lambda v: f"{v}%"),
        )
        fig_wr.update_layout(**PLOTLY_BASE, showlegend=False, coloraxis_showscale=False, xaxis_tickangle=-45)
        fig_wr.update_traces(textposition="outside", textfont_color="#f0f0f0")
        fig_wr.update_xaxes(gridcolor="#222")
        fig_wr.update_yaxes(gridcolor="#222")
        st.plotly_chart(fig_wr, use_container_width=True)


# ── Tab: Jogos ────────────────────────────────────────────────────────────────
with tab_jogos:
    st.markdown('<div class="section-title">JOGOS</div>', unsafe_allow_html=True)

    # Filtro de período dentro do tab
    if not league_fixtures_all.empty:
        min_date = league_fixtures_all["match_date"].min().date()
        max_date = league_fixtures_all["match_date"].max().date()
        date_range = st.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    else:
        date_range = None

    tab_fixtures = league_fixtures.copy()
    if date_range and len(date_range) == 2:
        tab_fixtures = tab_fixtures[
            (tab_fixtures["match_date"].dt.date >= date_range[0])
            & (tab_fixtures["match_date"].dt.date <= date_range[1])
        ]

    if not tab_fixtures.empty:
        tab_fixtures = tab_fixtures.sort_values("match_date", ascending=False)
        tab_fixtures["data_str"] = tab_fixtures["match_date"].dt.strftime("%Y-%m-%d")
        tab_fixtures["resultado_html"] = tab_fixtures["result"].apply(result_badge)

        disp_fix = tab_fixtures[["data_str", "round", "home_team", "home_goals", "away_goals", "away_team", "resultado_html"]].copy()
        disp_fix.columns = ["Data", "Jornada", "Casa", "GC", "GA", "Fora", "Resultado"]
        st.write(disp_fix.to_html(escape=False, index=False), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">GOLOS POR JORNADA (SELEÇÃO)</div>', unsafe_allow_html=True)
        goals_rnd = (
            tab_fixtures.groupby("round_num")["total_goals"]
            .agg(["mean", "sum", "count"])
            .reset_index()
            .rename(columns={"mean": "media", "sum": "total", "count": "jogos"})
        )
        if not goals_rnd.empty:
            fig_rnd = go.Figure([
                go.Scatter(
                    x=goals_rnd["round_num"], y=goals_rnd["media"],
                    mode="lines+markers", name="Média/jogo",
                    line=dict(color="#e94560", width=2), marker=dict(size=6),
                ),
                go.Bar(
                    x=goals_rnd["round_num"], y=goals_rnd["total"],
                    name="Total golos", marker_color="rgba(15,52,96,0.5)", yaxis="y2",
                ),
            ])
            fig_rnd.update_layout(
                **PLOTLY_BASE,
                yaxis=dict(title="Média/jogo", gridcolor="#222"),
                yaxis2=dict(title="Total golos", overlaying="y", side="right", gridcolor="#222"),
                xaxis=dict(title="Jornada", gridcolor="#222"),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_rnd, use_container_width=True)
    else:
        st.info("Sem jogos para os filtros selecionados.")


# ── Tab: Marcadores ───────────────────────────────────────────────────────────
with tab_marc:
    st.markdown('<div class="section-title">TOP MARCADORES</div>', unsafe_allow_html=True)

    if not league_scorers.empty:
        top10_sc = league_scorers[league_scorers["goals"] > 0].head(10).copy()
        top10_sc["goals_per_game"] = (top10_sc["goals"] / top10_sc["apps"].replace(0, pd.NA)).round(2)

        fig3 = px.bar(
            top10_sc, x="player", y="goals",
            color="goals", color_continuous_scale=["#0f3460", "#e94560"],
            text="goals", labels={"player": "", "goals": "Golos"},
        )
        fig3.update_layout(**PLOTLY_BASE, showlegend=False, coloraxis_showscale=False)
        fig3.update_traces(textposition="outside", textfont_color="#f0f0f0")
        fig3.update_xaxes(gridcolor="#222")
        fig3.update_yaxes(gridcolor="#222")
        st.plotly_chart(fig3, use_container_width=True)

        st.markdown('<div class="section-title">TABELA DETALHADA</div>', unsafe_allow_html=True)
        sc_table = top10_sc[["player", "team", "goals", "apps", "goals_per_game"]].copy()
        sc_table.columns = ["Jogador", "Equipa", "Golos", "Jogos", "Golos/Jogo"]
        sc_table.index = range(1, len(sc_table) + 1)
        st.dataframe(sc_table, use_container_width=True)

        st.markdown('<div class="section-title">GOLOS POR JOGO</div>', unsafe_allow_html=True)
        fig_gpg = px.scatter(
            top10_sc, x="apps", y="goals", text="player",
            size="goals", color="goals_per_game",
            color_continuous_scale=["#1a1a2e", "#e94560"],
            labels={"apps": "Jogos", "goals": "Golos", "goals_per_game": "Golos/Jogo"},
        )
        fig_gpg.update_traces(textposition="top center", textfont_color="#f0f0f0")
        fig_gpg.update_layout(**PLOTLY_BASE)
        fig_gpg.update_xaxes(gridcolor="#222")
        fig_gpg.update_yaxes(gridcolor="#222")
        st.plotly_chart(fig_gpg, use_container_width=True)


# ── Tab: Análise por Equipa ───────────────────────────────────────────────────
with tab_equipa:
    selected_team = st.selectbox("Equipa", all_teams_sorted, key="team_sel")

    if selected_team and not league_fixtures_all.empty:
        home_f = league_fixtures_all[league_fixtures_all["home_team"] == selected_team]
        away_f = league_fixtures_all[league_fixtures_all["away_team"] == selected_team]

        h_w = (home_f["result"] == "home").sum()
        h_d = (home_f["result"] == "draw").sum()
        h_l = (home_f["result"] == "away").sum()
        a_w = (away_f["result"] == "away").sum()
        a_d = (away_f["result"] == "draw").sum()
        a_l = (away_f["result"] == "home").sum()

        h_gf = int(home_f["home_goals"].sum())
        h_ga = int(home_f["away_goals"].sum())
        a_gf = int(away_f["away_goals"].sum())
        a_ga = int(away_f["home_goals"].sum())

        h_cs = (home_f["away_goals"] == 0).sum()
        a_cs = (away_f["home_goals"] == 0).sum()

        st.markdown("<br>", unsafe_allow_html=True)
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.markdown(metric_card(len(home_f) + len(away_f), "Jogos"), unsafe_allow_html=True)
        with k2:
            st.markdown(metric_card(int(h_w + a_w), "Vitórias"), unsafe_allow_html=True)
        with k3:
            st.markdown(metric_card(h_gf + a_gf, "Golos marcados"), unsafe_allow_html=True)
        with k4:
            st.markdown(metric_card(h_ga + a_ga, "Golos sofridos"), unsafe_allow_html=True)
        with k5:
            st.markdown(metric_card(int(h_cs + a_cs), "Clean sheets"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown('<div class="section-title">CASA VS FORA</div>', unsafe_allow_html=True)
            fig_ha = go.Figure([
                go.Bar(name="Casa", x=["Vitórias", "Empates", "Derrotas", "GM", "GS"],
                       y=[h_w, h_d, h_l, h_gf, h_ga], marker_color="#e94560"),
                go.Bar(name="Fora", x=["Vitórias", "Empates", "Derrotas", "GM", "GS"],
                       y=[a_w, a_d, a_l, a_gf, a_ga], marker_color="#0f3460"),
            ])
            fig_ha.update_layout(**PLOTLY_BASE, barmode="group", legend=dict(bgcolor="rgba(0,0,0,0)"))
            fig_ha.update_xaxes(gridcolor="#222")
            fig_ha.update_yaxes(gridcolor="#222")
            st.plotly_chart(fig_ha, use_container_width=True)

        with col_b:
            st.markdown('<div class="section-title">DISTRIBUIÇÃO RESULTADOS</div>', unsafe_allow_html=True)
            fig_pie = go.Figure(go.Pie(
                labels=["Vitórias", "Empates", "Derrotas"],
                values=[int(h_w + a_w), int(h_d + a_d), int(h_l + a_l)],
                hole=0.45,
                marker_colors=["#27ae60", "#f39c12", "#e74c3c"],
            ))
            fig_pie.update_layout(**PLOTLY_BASE)
            fig_pie.update_traces(textfont_color="#f0f0f0")
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown('<div class="section-title">GOLOS POR JORNADA</div>', unsafe_allow_html=True)
        all_team_f = pd.concat([
            home_f.assign(gf=home_f["home_goals"], ga=home_f["away_goals"]),
            away_f.assign(gf=away_f["away_goals"], ga=away_f["home_goals"]),
        ]).sort_values("round_num")

        if not all_team_f.empty:
            fig_grnd = go.Figure([
                go.Scatter(x=all_team_f["round_num"], y=all_team_f["gf"],
                           mode="lines+markers", name="Marcados",
                           line=dict(color="#e94560", width=2), marker=dict(size=6)),
                go.Scatter(x=all_team_f["round_num"], y=all_team_f["ga"],
                           mode="lines+markers", name="Sofridos",
                           line=dict(color="#0f3460", width=2), marker=dict(size=6)),
            ])
            fig_grnd.update_layout(**PLOTLY_BASE, legend=dict(bgcolor="rgba(0,0,0,0)"))
            fig_grnd.update_xaxes(gridcolor="#222", title="Jornada")
            fig_grnd.update_yaxes(gridcolor="#222", title="Golos")
            st.plotly_chart(fig_grnd, use_container_width=True)

        # Histórico de jogos da equipa
        st.markdown('<div class="section-title">HISTÓRICO</div>', unsafe_allow_html=True)
        hist = all_team_f.sort_values("match_date", ascending=False)
        hist["data_str"] = hist["match_date"].dt.strftime("%Y-%m-%d")

        def team_result_badge(row, team):
            if row["result"] == "draw":
                return result_badge("draw")
            winner = row["home_team"] if row["result"] == "home" else row["away_team"]
            return result_badge("home" if winner == team else "away")

        hist["res_html"] = hist.apply(lambda r: team_result_badge(r, selected_team), axis=1)
        hist_disp = hist[["data_str", "round", "home_team", "home_goals", "away_goals", "away_team", "res_html"]].copy()
        hist_disp.columns = ["Data", "Jornada", "Casa", "GC", "GA", "Fora", "Resultado"]
        st.write(hist_disp.to_html(escape=False, index=False), unsafe_allow_html=True)


# ── Tab: Head to Head ─────────────────────────────────────────────────────────
with tab_h2h:
    st.markdown('<div class="section-title">HEAD TO HEAD</div>', unsafe_allow_html=True)

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        team_a = st.selectbox("Equipa A", all_teams_sorted, key="h2h_a")
    with col_h2:
        others = [t for t in all_teams_sorted if t != team_a]
        team_b = st.selectbox("Equipa B", others, key="h2h_b")

    if team_a and team_b:
        h2h = league_fixtures_all[
            ((league_fixtures_all["home_team"] == team_a) & (league_fixtures_all["away_team"] == team_b))
            | ((league_fixtures_all["home_team"] == team_b) & (league_fixtures_all["away_team"] == team_a))
        ].copy()

        if not h2h.empty:
            a_wins = ((((h2h["home_team"] == team_a) & (h2h["result"] == "home"))
                       | ((h2h["away_team"] == team_a) & (h2h["result"] == "away")))).sum()
            b_wins = ((((h2h["home_team"] == team_b) & (h2h["result"] == "home"))
                       | ((h2h["away_team"] == team_b) & (h2h["result"] == "away")))).sum()
            draws_h2h = (h2h["result"] == "draw").sum()

            a_goals = int(h2h.apply(
                lambda r: r["home_goals"] if r["home_team"] == team_a else r["away_goals"], axis=1
            ).sum())
            b_goals = int(h2h.apply(
                lambda r: r["home_goals"] if r["home_team"] == team_b else r["away_goals"], axis=1
            ).sum())

            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                st.markdown(metric_card(int(a_wins), f"Vitórias {team_a[:15]}"), unsafe_allow_html=True)
            with k2:
                st.markdown(metric_card(int(draws_h2h), "Empates"), unsafe_allow_html=True)
            with k3:
                st.markdown(metric_card(int(b_wins), f"Vitórias {team_b[:15]}"), unsafe_allow_html=True)
            with k4:
                st.markdown(metric_card(a_goals, f"Golos {team_a[:15]}"), unsafe_allow_html=True)
            with k5:
                st.markdown(metric_card(b_goals, f"Golos {team_b[:15]}"), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Comparação visual
            fig_h2h = go.Figure([
                go.Bar(name=team_a, x=["Vitórias", "Golos"], y=[int(a_wins), a_goals], marker_color="#e94560"),
                go.Bar(name=team_b, x=["Vitórias", "Golos"], y=[int(b_wins), b_goals], marker_color="#0f3460"),
            ])
            fig_h2h.update_layout(**PLOTLY_BASE, barmode="group", legend=dict(bgcolor="rgba(0,0,0,0)"))
            fig_h2h.update_xaxes(gridcolor="#222")
            fig_h2h.update_yaxes(gridcolor="#222")
            st.plotly_chart(fig_h2h, use_container_width=True)

            # Histórico de confrontos
            st.markdown('<div class="section-title">HISTÓRICO DE CONFRONTOS</div>', unsafe_allow_html=True)
            h2h = h2h.sort_values("match_date", ascending=False)
            h2h["data_str"] = h2h["match_date"].dt.strftime("%Y-%m-%d")

            def h2h_badge(row):
                if row["result"] == "draw":
                    return result_badge("draw")
                winner = row["home_team"] if row["result"] == "home" else row["away_team"]
                return f'<span class="result-badge" style="background:{"#27ae60" if winner == team_a else "#e74c3c"}">{"V " + team_a[:10] if winner == team_a else "V " + team_b[:10]}</span>'

            h2h["res_html"] = h2h.apply(h2h_badge, axis=1)
            h2h_disp = h2h[["data_str", "home_team", "home_goals", "away_goals", "away_team", "res_html"]].copy()
            h2h_disp.columns = ["Data", "Casa", "GC", "GA", "Fora", "Resultado"]
            st.write(h2h_disp.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.info(f"Sem jogos entre {team_a} e {team_b} nos dados disponíveis.")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#444; font-family:Inter; font-size:0.8rem'>"
    "Football Analytics · Pipeline ETL com Airflow, dbt e DuckDB · Dados via API-Football"
    "</p>",
    unsafe_allow_html=True,
)
