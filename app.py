from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Air Traffic | TU Delft",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "processed_data"
FLIGHTS = DATA / "flights_processed.parquet"
ROUTES = DATA / "route_pairs.parquet"
AIRPORTS = DATA / "airport_summary.parquet"
MONTHLY = DATA / "monthly_summary.parquet"
REPORT = DATA / "preprocessing_report.json"
UNMATCHED = DATA / "unmatched_airports.csv"
VALIDATION = DATA / "validation_results.csv"
LOGO = ROOT / "assets" / "tudelft_wordmark.svg"

# TU Delft-inspired cyan / deep navy palette. The logo asset is a compact
# dashboard wordmark; see README for the official corporate identity page.
CYAN = "#00A6D6"
NAVY = "#082B45"
INK = "#102A43"
MUTED = "#627D98"
PALE = "#EAF7FB"

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
      html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
      .stApp { background: #F5F8FA; color: #102A43; }
      [data-testid="stHeader"] { background: rgba(245,248,250,.92); }
      .block-container { padding-top: 1.15rem; padding-bottom: 2.5rem; max-width: 1600px; }
      [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E5EDF2; }
      [data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #E5EDF2; border-radius: 13px;
        padding: 13px 16px; box-shadow: 0 2px 8px rgba(8,43,69,.035);
      }
      [data-testid="stMetricLabel"] { color: #627D98; font-size: .82rem; }
      [data-testid="stMetricValue"] { color: #082B45; font-weight: 700; }
      div[data-testid="stTabs"] button { font-weight: 600; }
      div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #007FA8; border-bottom-color: #00A6D6;
      }
      .hero {
        background: linear-gradient(110deg, #082B45 0%, #0C4665 68%, #087FA4 100%);
        border-radius: 18px; padding: 22px 26px; color: white; margin-bottom: 18px;
      }
      .hero h1 { color: white; font-size: 2rem; margin: 0; font-weight: 700; letter-spacing: -.04em; }
      .hero p { color: #D8EEF5; margin: 4px 0 0 0; font-size: .9rem; }
      .section-kicker { color: #627D98; text-transform: uppercase; letter-spacing: .09em;
        font-size: .72rem; font-weight: 700; margin: 3px 0 7px 0; }
      .mini-note { color: #627D98; font-size: .78rem; }
      .stDownloadButton button { border-radius: 9px; }
      div[data-testid="stDataFrame"] { border: 1px solid #E5EDF2; border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Cached data access. DuckDB scans Parquet columns on demand instead of
# materialising all 16m flight rows into Streamlit's Python memory.
# ---------------------------------------------------------------------
@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=":memory:")


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


@st.cache_data(show_spinner=False, ttl=3600)
def parquet_columns(path: str, mtime: int) -> list[str]:
    con = get_connection()
    return [r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{path}')"
    ).fetchall()]


@st.cache_data(show_spinner="Reading dashboard dimensions…", ttl=3600)
def load_small_parquets(routes_path: str, airports_path: str, monthly_path: str,
                        routes_mtime: int, airports_mtime: int, monthly_mtime: int):
    con = get_connection()
    routes = con.execute(
        f"SELECT * FROM read_parquet('{routes_path}')"
    ).df()
    airports = con.execute(
        f"SELECT * FROM read_parquet('{airports_path}')"
    ).df()
    monthly = con.execute(
        f"SELECT * FROM read_parquet('{monthly_path}')"
    ).df()
    return routes, airports, monthly


@st.cache_data(show_spinner=False, ttl=1800)
def run_sql(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    return get_connection().execute(sql, list(params)).df()


def build_where(start_date, end_date, operators, airports, aircraft, search):
    clauses = ["try_cast(f.flight_date AS DATE) BETWEEN ? AND ?"]
    params: list[Any] = [start_date, end_date]
    if operators:
        clauses.append(f"f.icao_operator IN ({','.join(['?'] * len(operators))})")
        params.extend(operators)
    if airports:
        clauses.append("(f.adep IN ({}) OR f.ades IN ({}))".format(
            ",".join(["?"] * len(airports)), ",".join(["?"] * len(airports))
        ))
        params.extend(airports)
        params.extend(airports)
    if aircraft:
        clauses.append(f"f.typecode IN ({','.join(['?'] * len(aircraft))})")
        params.extend(aircraft)
    if search:
        searchable = ["f.icao_operator", "f.adep", "f.ades", "f.callsign",
                      "f.icao24", "f.registration", "f.typecode", "f.model"]
        clauses.append("(" + " OR ".join(
            [f"upper(coalesce(cast({c} AS VARCHAR),'')) LIKE ?" for c in searchable]
        ) + ")")
        params.extend([f"%{search.upper()}%"] * len(searchable))
    return " AND ".join(clauses), tuple(params)


def q_flights(where: str, params: tuple, select: str, group: str = "",
              order: str = "", limit: int | None = None) -> pd.DataFrame:
    sql = f"""
        SELECT {select}
        FROM flights f
        WHERE {where}
        {group}
        {order}
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return run_sql(sql, params)



def q_airport_activity(where: str, params: tuple) -> pd.DataFrame:
    # A departure and an arrival both count as an airport movement.
    sql = f"""
        WITH airport_counts AS (
            SELECT f.adep AS airport_code, count(*) AS departures, 0 AS arrivals
            FROM flights f
            WHERE {where} AND f.adep IS NOT NULL
            GROUP BY f.adep
            UNION ALL
            SELECT f.ades AS airport_code, 0 AS departures, count(*) AS arrivals
            FROM flights f
            WHERE {where} AND f.ades IS NOT NULL
            GROUP BY f.ades
        )
        SELECT airport_code, sum(departures) AS departures,
               sum(arrivals) AS arrivals,
               sum(departures + arrivals) AS movements
        FROM airport_counts
        GROUP BY airport_code
        ORDER BY movements DESC
    """
    return run_sql(sql, params + params)

def fmt_num(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{int(x):,}"


def metric_row(values):
    cols = st.columns(len(values))
    for col, (label, value, delta) in zip(cols, values):
        col.metric(label, value, delta)


def empty_state(message="No records match these filters."):
    st.info(message)


# ---------------------------------------------------------------------
# File checks and reference metadata
# ---------------------------------------------------------------------
missing = [p.name for p in [FLIGHTS, ROUTES, AIRPORTS, MONTHLY] if not p.is_file()]
if missing:
    st.error("Processed datasets are missing: " + ", ".join(missing))
    st.markdown(
        """
        Place the four files produced by the preprocessing notebook in
        `processed_data/` beside `app.py`:
        - `flights_processed.parquet`
        - `route_pairs.parquet`
        - `airport_summary.parquet`
        - `monthly_summary.parquet`
        """
    )
    st.stop()

try:
    flights_path = sql_path(FLIGHTS)
    flight_cols = parquet_columns(flights_path, FLIGHTS.stat().st_mtime_ns)
    route_df, airport_df, monthly_df = load_small_parquets(
        sql_path(ROUTES), sql_path(AIRPORTS), sql_path(MONTHLY),
        ROUTES.stat().st_mtime_ns, AIRPORTS.stat().st_mtime_ns,
        MONTHLY.stat().st_mtime_ns
    )
except Exception as exc:
    st.error(f"Could not read the processed Parquet datasets: {exc}")
    st.stop()

required = {"id", "flight_date", "icao_operator", "adep", "ades"}
if not required.issubset(set(flight_cols)):
    st.error("The flight-level Parquet is missing required fields: " +
             ", ".join(sorted(required - set(flight_cols))))
    st.stop()

optional_columns = {
    "icao24": "VARCHAR", "typecode": "VARCHAR", "model": "VARCHAR",
    "icao_aircraft_class": "VARCHAR", "registration": "VARCHAR",
    "callsign": "VARCHAR", "observation_span_min": "DOUBLE",
}
missing_optional = [
    f"NULL::{dtype} AS {name}"
    for name, dtype in optional_columns.items() if name not in flight_cols
]
extra_sql = (", " + ", ".join(missing_optional)) if missing_optional else ""
get_connection().execute(
    f"CREATE OR REPLACE VIEW flights AS "
    f"SELECT *{extra_sql} FROM read_parquet('{flights_path}')"
)

date_info = run_sql(
    """SELECT min(try_cast(flight_date AS DATE)) AS min_date,
              max(try_cast(flight_date AS DATE)) AS max_date
       FROM flights"""
)
min_date = pd.to_datetime(date_info.loc[0, "min_date"]).date()
max_date = pd.to_datetime(date_info.loc[0, "max_date"]).date()

# Lightweight filter options
option_sql = f"FROM flights"
operator_options = run_sql(
    f"""SELECT DISTINCT trim(icao_operator) AS icao_operator {option_sql}
        WHERE icao_operator IS NOT NULL
          AND trim(icao_operator) <> ''
          AND upper(trim(icao_operator)) NOT IN ('NONE', 'NULL', 'NAN', 'UNKNOWN')
        ORDER BY icao_operator"""
)["icao_operator"].astype(str).tolist()
aircraft_options = run_sql(
    f"""SELECT DISTINCT upper(trim(typecode)) AS typecode {option_sql}
        WHERE typecode IS NOT NULL
          AND trim(typecode) <> ''
          AND upper(trim(typecode)) NOT IN ('NONE', 'NULL', 'NAN', 'UNKNOWN')
        ORDER BY typecode"""
)["typecode"].astype(str).tolist()
airport_options = sorted(set(airport_df.get("airport_code", pd.Series(dtype=str)).dropna().astype(str)))


# ---------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width=155)
    st.markdown("### Filters")
    date_range = st.date_input(
        "Flight date (UTC)", value=(min_date, max_date),
        min_value=min_date, max_value=max_date, format="DD/MM/YYYY",
        key="date_range"
    )
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        date_start, date_end = date_range
    else:
        date_start = date_end = date_range
    selected_operators = st.multiselect("Airline / operator", operator_options,
                                        placeholder="All operators", key="selected_operators")
    selected_airports = st.multiselect("Airport", airport_options,
                                       placeholder="All airports", key="selected_airports")
    selected_aircraft = st.multiselect("Aircraft type", aircraft_options,
                                       placeholder="All aircraft", key="selected_aircraft")
    search = st.text_input("Quick search", placeholder="Callsign, registration, ICAO…", key="search")
    st.divider()
    if st.button("Reset filters", use_container_width=True):
        for widget_key in ["date_range", "selected_operators",
                           "selected_airports", "selected_aircraft", "search"]:
            st.session_state.pop(widget_key, None)
        st.rerun()
    st.caption(f"Data period: {min_date:%d %b %Y} — {max_date:%d %b %Y}")
    st.caption("OPDI flight-list · processed Parquet")


where, params = build_where(
    date_start, date_end, selected_operators, selected_airports,
    selected_aircraft, search.strip()
)

# Header
left, right = st.columns([5, 1])
with left:
    st.markdown(
        '<div class="hero"><h1>Air Traffic</h1>'
        '<p>Operational performance · network · airlines · fleet</p></div>',
        unsafe_allow_html=True
    )
with right:
    if LOGO.exists():
        st.image(str(LOGO), width=135)


# ---------------------------------------------------------------------
# Cohort KPIs and tabs
# ---------------------------------------------------------------------
kpi = q_flights(
    where, params,
    """count(*) AS flights,
       count(DISTINCT icao_operator) AS operators,
       count(DISTINCT icao24) AS aircraft,
       count(DISTINCT CASE WHEN adep IS NOT NULL AND ades IS NOT NULL
                           THEN adep || '|' || ades END) AS routes,
       median(observation_span_min) AS median_span"""
)
airport_count_sql = f"""
    SELECT count(DISTINCT airport_code) AS airports
    FROM (
        SELECT f.adep AS airport_code
        FROM flights f WHERE {where} AND f.adep IS NOT NULL
        UNION
        SELECT f.ades AS airport_code
        FROM flights f WHERE {where} AND f.ades IS NOT NULL
    ) a
"""
airport_count = run_sql(airport_count_sql, params + params).iloc[0]["airports"]
r = kpi.iloc[0]
metric_row([
    ("Flights", fmt_num(r["flights"]), None),
    ("Airlines", fmt_num(r["operators"]), None),
    ("Aircraft", fmt_num(r["aircraft"]), None),
    ("Airports", fmt_num(airport_count), None),
    ("Routes", fmt_num(r["routes"]), None),
    ("Median observation span", f"{r['median_span']:.0f} min" if pd.notna(r["median_span"]) else "—", None),
])

tabs = st.tabs(["Overview", "Network map", "Airlines", "Airports", "Fleet", "Routes", "Flight explorer", "Data quality"])


# ---------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------
with tabs[0]:
    st.markdown('<div class="section-kicker">Traffic pulse</div>', unsafe_allow_html=True)
    monthly = q_flights(
        where, params,
        """strftime(try_cast(flight_date AS DATE), '%Y-%m') AS month,
           count(*) AS flights,
           count(DISTINCT icao_operator) AS airlines,
           count(DISTINCT icao24) AS aircraft""",
        group="GROUP BY 1", order="ORDER BY 1"
    )
    if monthly.empty:
        empty_state()
    else:
        c1, c2 = st.columns([1.7, 1])
        with c1:
            fig = px.area(monthly, x="month", y="flights", markers=True,
                          title="Monthly traffic", color_discrete_sequence=[CYAN])
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=50, b=10),
                              xaxis_title=None, yaxis_title="Flight records",
                              plot_bgcolor="white", paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(monthly, x="month", y="aircraft", title="Unique aircraft by month",
                         color_discrete_sequence=[NAVY])
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=50, b=10),
                              xaxis_title=None, yaxis_title="Aircraft",
                              plot_bgcolor="white", paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    with a:
        leaders_where = (
            f"({where}) AND f.icao_operator IS NOT NULL "
            "AND trim(f.icao_operator) <> '' "
            "AND upper(trim(f.icao_operator)) NOT IN ('NONE', 'NULL', 'NAN', 'UNKNOWN')"
        )
        leaders = q_flights(
            leaders_where, params,
            """icao_operator AS airline, count(*) AS flights,
               count(DISTINCT icao24) AS aircraft,
               count(DISTINCT adep || '|' || ades) AS routes""",
            group="GROUP BY 1", order="ORDER BY flights DESC", limit=12
        )
        if not leaders.empty:
            fig = px.bar(leaders.sort_values("flights"), x="flights", y="airline",
                         orientation="h", title="Top airlines",
                         color_discrete_sequence=[CYAN],
                         hover_data=["aircraft", "routes"])
            fig.update_layout(height=410, margin=dict(l=10, r=10, t=50, b=10),
                              yaxis_title=None, plot_bgcolor="white", paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
    with b:
        busy = q_airport_activity(where, params).head(12)
        if not busy.empty:
            fig = px.bar(busy.sort_values("movements"), x="movements", y="airport_code",
                         orientation="h", title="Busiest airports · movements",
                         color_discrete_sequence=[NAVY])
            fig.update_layout(height=410, margin=dict(l=10, r=10, t=50, b=10),
                              yaxis_title=None, plot_bgcolor="white", paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------
# Network map
# ---------------------------------------------------------------------
with tabs[1]:
    map_controls = st.columns([1, 1, 2])
    top_n = map_controls[0].select_slider("Routes shown", options=[50, 100, 250, 500, 1000], value=250)
    map_controls[1].selectbox("Map focus", ["Global", "Europe", "North America", "Asia"], key="map_focus")
    map_controls[2].caption("Airport-to-airport network links · not radar tracks")
    # Aggregate filtered flights first, then match coordinates, then apply
    # the slider. This prevents unmapped high-volume routes from consuming
    # the top-N limit and leaving the map empty.
    route_data = q_flights(
        where, params,
        """f.adep, f.ades, count(*) AS flights""",
        group="GROUP BY f.adep, f.ades",
        order="ORDER BY flights DESC"
    )
    if not route_data.empty:
        coords = route_df[[
            "adep", "ades", "origin_latitude", "origin_longitude",
            "destination_latitude", "destination_longitude"
        ]].drop_duplicates(["adep", "ades"])
        route_data = route_data.merge(coords, on=["adep", "ades"], how="left")
        route_data = route_data.dropna(subset=[
            "origin_latitude", "origin_longitude",
            "destination_latitude", "destination_longitude"
        ])
        route_data = (
            route_data.sort_values("flights", ascending=False)
            .head(int(top_n))
            .reset_index(drop=True)
        )
    if route_data.empty:
        empty_state("No mapped routes are available for this selection.")
    else:
        lons, lats = [], []
        for row in route_data.itertuples():
            lons.extend([row.origin_longitude, row.destination_longitude, None])
            lats.extend([row.origin_latitude, row.destination_latitude, None])
        fig = go.Figure()
        fig.add_trace(go.Scattergeo(
            lon=lons, lat=lats, mode="lines",
            line=dict(width=1.15, color=CYAN), opacity=.32,
            hoverinfo="skip", name="Routes"
        ))
        fig.add_trace(go.Scattergeo(
            lon=(route_data.origin_longitude + route_data.destination_longitude) / 2,
            lat=(route_data.origin_latitude + route_data.destination_latitude) / 2,
            mode="markers",
            marker=dict(size=np.clip(4 + np.sqrt(route_data.flights) / 9, 4, 13),
                        color="#F59E0B", opacity=.8),
            text=[f"{x} → {y}<br>{n:,} flights" for x, y, n in
                  zip(route_data.adep, route_data.ades, route_data.flights)],
            hovertemplate="%{text}<extra></extra>", name="Route volume"
        ))
        airports_used = pd.concat([
            route_data[["adep", "origin_latitude", "origin_longitude"]].rename(
                columns={"adep": "code", "origin_latitude": "lat", "origin_longitude": "lon"}),
            route_data[["ades", "destination_latitude", "destination_longitude"]].rename(
                columns={"ades": "code", "destination_latitude": "lat", "destination_longitude": "lon"})
        ]).drop_duplicates("code")
        fig.add_trace(go.Scattergeo(
            lon=airports_used.lon, lat=airports_used.lat, mode="markers",
            marker=dict(size=5, color=NAVY, opacity=.9),
            text=airports_used.code, hovertemplate="%{text}<extra>Airport</extra>",
            name="Airports"
        ))
        focus = st.session_state.get("map_focus", "Global")
        projection = "natural earth"
        geo = dict(showland=True, landcolor="#EDF2F5", showocean=True,
                   oceancolor="#F8FBFC", showcountries=True, countrycolor="#C7D4DC",
                   showcoastlines=True, coastlinecolor="#AEBFC9",
                   bgcolor="rgba(0,0,0,0)")
        if focus == "Europe":
            geo.update(projection_type="mercator", lataxis_range=[30, 72], lonaxis_range=[-25, 45])
        elif focus == "North America":
            geo.update(projection_type="mercator", lataxis_range=[5, 75], lonaxis_range=[-170, -45])
        elif focus == "Asia":
            geo.update(projection_type="mercator", lataxis_range=[-10, 75], lonaxis_range=[35, 180])
        else:
            geo.update(projection_type=projection)
        fig.update_layout(height=650, margin=dict(l=0, r=0, t=5, b=0),
                          paper_bgcolor="white", geo=geo,
                          legend=dict(orientation="h", y=0.02, x=0.02))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(route_data[["adep", "ades", "flights"]].head(30),
                     use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------
# Airlines
# ---------------------------------------------------------------------
with tabs[2]:
    airline_where = (
        f"({where}) AND f.icao_operator IS NOT NULL "
        "AND trim(f.icao_operator) <> '' "
        "AND upper(trim(f.icao_operator)) NOT IN ('NONE', 'NULL', 'NAN', 'UNKNOWN')"
    )
    airline = q_flights(
        airline_where, params,
        """icao_operator AS airline, count(*) AS flights,
           count(DISTINCT icao24) AS aircraft,
           count(DISTINCT typecode) AS aircraft_types,
           count(DISTINCT adep || '|' || ades) AS routes,
           median(observation_span_min) AS median_span""",
        group="GROUP BY 1", order="ORDER BY flights DESC"
    )
    if airline.empty:
        empty_state()
    else:
        c1, c2 = st.columns([1.5, 1])
        with c1:
            fig = px.bar(airline.head(25).sort_values("flights"), x="flights", y="airline",
                         orientation="h", title="Airline traffic ranking",
                         color_discrete_sequence=[CYAN],
                         hover_data=["aircraft", "aircraft_types", "routes", "median_span"])
            fig.update_layout(height=620, yaxis_title=None, plot_bgcolor="white",
                              paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.scatter(airline, x="aircraft", y="flights", size="routes",
                             color="median_span", hover_name="airline",
                             title="Scale vs traffic", color_continuous_scale="Teal")
            fig.update_layout(height=620, plot_bgcolor="white", paper_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(airline, use_container_width=True, hide_index=True)
        st.download_button("Download airline table",
                           airline.to_csv(index=False).encode("utf-8"),
                           "airline_performance.csv", "text/csv")


# ---------------------------------------------------------------------
# Airports
# ---------------------------------------------------------------------
with tabs[3]:
    airport_activity = q_airport_activity(where, params)
    if airport_activity.empty:
        empty_state()
    else:
        airport_activity = airport_activity.merge(
            airport_df[["airport_code", "airport_name", "municipality", "iso_country",
                        "latitude_deg", "longitude_deg"]].drop_duplicates("airport_code"),
            on="airport_code", how="left"
        )
        airport_activity["iso_country"] = airport_activity["iso_country"].fillna("Unmatched / unknown")
        airport_activity["airport_name"] = airport_activity["airport_name"].fillna("Airport name unavailable")
        airport_activity["departure_share_pct"] = np.where(
            airport_activity["movements"] > 0,
            100 * airport_activity["departures"] / airport_activity["movements"],
            np.nan
        )
        airport_activity["balance"] = airport_activity["departures"] - airport_activity["arrivals"]

        st.markdown('<div class="section-kicker">Airport activity</div>', unsafe_allow_html=True)
        airport_top_n = st.select_slider(
            "Airports in visualisations",
            options=[20, 30, 50, 75, 100, 150, 250],
            value=75,
            key="airport_top_n"
        )
        airport_view = airport_activity.head(int(airport_top_n)).copy()

        c1, c2 = st.columns([1.15, 1])
        with c1:
            treemap = px.treemap(
                airport_view,
                path=[px.Constant("All airports"), "iso_country", "airport_code"],
                values="movements",
                color="departure_share_pct",
                color_continuous_scale="Teal",
                range_color=[0, 100],
                hover_data={
                    "airport_name": True,
                    "departures": ":,",
                    "arrivals": ":,",
                    "movements": ":,",
                    "departure_share_pct": ":.1f",
                },
                title="Airport traffic footprint · click to drill down"
            )
            treemap.update_traces(
                root_color="#EAF2F6",
                marker=dict(line=dict(color="white", width=1.5))
            )
            treemap.update_layout(
                height=570, margin=dict(l=8, r=8, t=55, b=8),
                paper_bgcolor="white",
                coloraxis_colorbar=dict(title="Departure<br>share (%)")
            )
            st.plotly_chart(treemap, use_container_width=True)

        with c2:
            balance_color = st.selectbox(
                "Colour airports by",
                ["Departure share", "Country", "Net movement balance"],
                key="airport_balance_colour"
            )
            color_col = {
                "Departure share": "departure_share_pct",
                "Country": "iso_country",
                "Net movement balance": "balance",
            }[balance_color]
            scatter = px.scatter(
                airport_view,
                x="departures", y="arrivals",
                size="movements", color=color_col,
                hover_name="airport_code",
                hover_data={
                    "airport_name": True,
                    "iso_country": True,
                    "departures": ":,",
                    "arrivals": ":,",
                    "movements": ":,",
                    "balance": ":,",
                    "departure_share_pct": ":.1f",
                },
                size_max=38,
                color_continuous_scale="Teal",
                title="Departure / arrival balance"
            )
            max_axis = max(
                float(airport_view["departures"].max()),
                float(airport_view["arrivals"].max()),
                1.0
            )
            scatter.add_shape(
                type="line", x0=0, y0=0, x1=max_axis, y1=max_axis,
                line=dict(color="#829AB1", width=1.5, dash="dash")
            )
            scatter.add_annotation(
                x=max_axis * .72, y=max_axis * .76,
                text="Balanced", showarrow=False,
                font=dict(color="#627D98", size=11)
            )
            scatter.update_layout(
                height=570, margin=dict(l=8, r=8, t=55, b=8),
                paper_bgcolor="white",
                xaxis_title="Departures", yaxis_title="Arrivals",
                xaxis=dict(rangemode="tozero", gridcolor="#EAF0F4"),
                yaxis=dict(rangemode="tozero", gridcolor="#EAF0F4"),
            )
            st.plotly_chart(scatter, use_container_width=True)

        st.markdown('<div class="section-kicker">Airport ranking</div>', unsafe_allow_html=True)
        st.dataframe(
            airport_activity, use_container_width=True, hide_index=True,
            column_config={
                "departures": st.column_config.NumberColumn("Departures", format="%d"),
                "arrivals": st.column_config.NumberColumn("Arrivals", format="%d"),
                "movements": st.column_config.NumberColumn("Total movements", format="%d"),
                "departure_share_pct": st.column_config.NumberColumn("Departure share", format="%.1f%%"),
                "balance": st.column_config.NumberColumn("Net balance", format="%d"),
            }
        )
        st.download_button(
            "Download airport table",
            airport_activity.to_csv(index=False).encode("utf-8"),
            "airport_activity.csv", "text/csv"
        )


with tabs[4]:
    fleet = q_flights(
        where, params,
        """upper(trim(f.typecode)) AS typecode,
           max(nullif(trim(f.model), '')) AS model,
           max(nullif(trim(f.icao_aircraft_class), '')) AS aircraft_class,
           count(*) AS flights,
           count(DISTINCT f.icao24) AS aircraft,
           count(DISTINCT f.icao_operator) AS operators,
           median(f.observation_span_min) AS median_span""",
        group="GROUP BY 1",
        order="ORDER BY flights DESC"
    )
    # Missing typecodes are shown separately, not as a fake "Unknown" aircraft.
    fleet = fleet.loc[
        fleet["typecode"].notna()
        & fleet["typecode"].astype(str).str.strip().ne("")
        & ~fleet["typecode"].astype(str).str.upper().isin(["NONE", "NULL", "NAN", "UNKNOWN"])
    ].copy()
    total_flights = int(q_flights(where, params, "count(*) AS flights").iloc[0]["flights"])
    typed_flights = int(q_flights(
        f"({where}) AND f.typecode IS NOT NULL AND trim(f.typecode) <> '' "
        "AND upper(trim(f.typecode)) NOT IN ('NONE', 'NULL', 'NAN', 'UNKNOWN')",
        params, "count(*) AS flights"
    ).iloc[0]["flights"])
    missing_flights = total_flights - typed_flights

    if fleet.empty:
        empty_state("No aircraft typecodes are available for the selected filters.")
    else:
        c1, c2 = st.columns([1.2, 1])
        with c1:
            fig = px.bar(
                fleet.head(30).sort_values("flights"),
                x="flights", y="typecode", orientation="h",
                title="Most-used aircraft types",
                color_discrete_sequence=[CYAN],
                hover_data=["model", "aircraft", "operators", "aircraft_class"]
            )
            fig.update_layout(
                height=650, yaxis_title=None, plot_bgcolor="white",
                paper_bgcolor="white", margin=dict(l=8, r=8, t=55, b=8)
            )
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            class_mix = (
                fleet.loc[
                    fleet["aircraft_class"].notna()
                    & fleet["aircraft_class"].astype(str).str.strip().ne("")
                    & ~fleet["aircraft_class"].astype(str).str.upper().isin(
                        ["NONE", "NULL", "NAN", "UNKNOWN"]
                    )
                ]
                .groupby("aircraft_class", as_index=False)["flights"].sum()
                .sort_values("flights", ascending=False)
            )
            if class_mix.empty:
                st.info("Aircraft class is not populated in the selected records.")
            else:
                fig = px.pie(
                    class_mix, names="aircraft_class", values="flights",
                    hole=.58, title="Traffic by aircraft class",
                    color_discrete_sequence=px.colors.sequential.Teal
                )
                fig.update_layout(
                    height=650, paper_bgcolor="white",
                    margin=dict(l=8, r=8, t=55, b=8)
                )
                st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Flights with a typecode", fmt_num(typed_flights))
        m2.metric("Distinct typecodes", fmt_num(fleet["typecode"].nunique()))
        m3.metric("Flights without a typecode", fmt_num(missing_flights),
                  f"{100 * missing_flights / total_flights:.1f}% of flights" if total_flights else None)
        st.dataframe(fleet, use_container_width=True, hide_index=True)
        st.download_button(
            "Download fleet table",
            fleet.to_csv(index=False).encode("utf-8"),
            "fleet_performance.csv", "text/csv"
        )


with tabs[5]:
    route_limit = st.select_slider(
        "Routes in ranking",
        options=[25, 50, 100, 250, 500],
        value=100,
        key="route_table_limit"
    )
    routes_where = (
        f"({where}) AND f.adep IS NOT NULL AND trim(f.adep) <> '' "
        "AND f.ades IS NOT NULL AND trim(f.ades) <> ''"
    )
    routes = q_flights(
        routes_where, params,
        """f.adep, f.ades,
           f.adep || ' → ' || f.ades AS route,
           count(*) AS flights,
           count(DISTINCT f.icao_operator) AS airlines,
           count(DISTINCT f.icao24) AS aircraft,
           count(DISTINCT f.typecode) AS aircraft_types,
           median(f.observation_span_min) AS median_span""",
        group="GROUP BY f.adep, f.ades",
        order="ORDER BY flights DESC",
        limit=10000
    )
    if routes.empty:
        empty_state("No flights with both departure and destination airports match the current filters.")
        st.caption("Try widening the date range or clearing the airline, airport, aircraft and text filters.")
    else:
        routes = routes.sort_values("flights", ascending=False).reset_index(drop=True)
        visible_routes = routes.head(int(route_limit)).copy()
        st.caption(f"{fmt_num(len(routes))} directional routes match the current filters.")
        c1, c2 = st.columns([1, 1])
        with c1:
            fig = px.bar(
                visible_routes.sort_values("flights"),
                x="flights", y="route", orientation="h",
                title=f"Top {min(route_limit, len(routes))} directional routes",
                color_discrete_sequence=[CYAN],
                hover_data=["airlines", "aircraft", "aircraft_types", "median_span"]
            )
            fig.update_layout(
                height=650, yaxis_title=None, plot_bgcolor="white",
                paper_bgcolor="white", margin=dict(l=8, r=8, t=55, b=8)
            )
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.scatter(
                routes, x="aircraft", y="flights", size="airlines",
                color="aircraft_types", hover_name="route",
                title="Route traffic vs fleet diversity",
                hover_data=["median_span"], color_continuous_scale="Teal"
            )
            fig.update_layout(
                height=650, plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(l=8, r=8, t=55, b=8)
            )
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(visible_routes, use_container_width=True, hide_index=True)
        st.download_button(
            "Download route table",
            routes.to_csv(index=False).encode("utf-8"),
            "route_performance.csv", "text/csv"
        )


with tabs[6]:
    st.markdown('<div class="section-kicker">Record-level exploration</div>', unsafe_allow_html=True)
    page_size = st.select_slider(
        "Rows to display",
        options=[100, 250, 500, 1000, 2000],
        value=500,
        key="explorer_page_size"
    )
    explorer = q_flights(
        where, params,
        """try_cast(f.flight_date AS DATE) AS flight_date,
           f.icao_operator, f.callsign, f.adep, f.ades,
           f.typecode, f.model, f.registration, f.icao24,
           f.observation_span_min""",
        order="ORDER BY try_cast(f.flight_date AS DATE) DESC NULLS LAST",
        limit=page_size
    )
    if explorer.empty:
        empty_state("No flight records match the current filters.")
        st.caption("Try widening the date range or clearing the filters in the sidebar.")
    else:
        st.caption(f"Showing {len(explorer):,} records from the filtered flight population.")
        st.dataframe(
            explorer, use_container_width=True, hide_index=True,
            column_config={
                "flight_date": st.column_config.DateColumn("Flight date", format="DD MMM YYYY"),
                "observation_span_min": st.column_config.NumberColumn(
                    "Observation span (min)", format="%.1f"
                ),
            }
        )
        st.download_button(
            "Download visible records",
            explorer.to_csv(index=False).encode("utf-8"),
            "flight_explorer.csv", "text/csv"
        )


with tabs[7]:
    if REPORT.exists():
        import json
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        a, b, c, d = st.columns(4)
        a.metric("Source files", fmt_num(report.get("source_file_count")))
        b.metric("Accepted flights", fmt_num(report.get("accepted_unique_flight_ids")))
        c.metric("Exact duplicates removed", fmt_num(report.get("exact_duplicate_rows_removed")))
        d.metric("Unmapped airport codes", fmt_num(report.get("unmatched_or_ambiguous_airport_codes")))
        checks = pd.DataFrame(report.get("validation_checks", []))
        if not checks.empty:
            checks["status"] = np.where(checks["passed"], "PASS", "FAIL")
            st.dataframe(checks[["check", "status", "detail"]],
                         use_container_width=True, hide_index=True)
        st.caption("Airport coordinates are airport locations. Route lines show network links, not flown trajectories.")
        st.caption("Observation span = last_seen − first_seen; it is not confirmed block time.")
    if UNMATCHED.exists():
        unmatched = pd.read_csv(UNMATCHED)
        st.subheader("Unmatched / ambiguous airport codes")
        st.dataframe(unmatched, use_container_width=True, hide_index=True)
        st.download_button("Download unmatched airports",
                           unmatched.to_csv(index=False).encode("utf-8"),
                           "unmatched_airports.csv", "text/csv")
    if VALIDATION.exists():
        validation = pd.read_csv(VALIDATION)
        st.subheader("Validation log")
        st.dataframe(validation, use_container_width=True, hide_index=True)

st.markdown(
    '<div class="mini-note" style="text-align:center;padding-top:20px;">'
    'Air Traffic Dashboard · OPDI flight-list data · TU Delft-inspired student project'
    '</div>',
    unsafe_allow_html=True
)
