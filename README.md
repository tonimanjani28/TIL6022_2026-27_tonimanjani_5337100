# Air Traffic — operational performance dashboard

A redesigned Streamlit dashboard for the processed 2025 OPDI flight-list data.

## What's included

- Compact **Air Traffic** title and TU Delft-inspired wordmark
- Global / regional route map
- Interactive filters for date, airline/operator, airport, aircraft type and free-text search
- Overview: monthly traffic, airline leaders, airport movements
- Airline performance: flight counts, aircraft, route breadth and observation-span proxy
- Airport activity: departures, arrivals, total movements and country/location metadata
- Fleet: aircraft types, models, classes and unique aircraft
- Directional route rankings and route diversity
- Record-level flight explorer with CSV export
- Data-quality and preprocessing validation page
- DuckDB queries directly against Parquet: the app does not load all 16m flight records into pandas memory

## Install / run (Windows Anaconda Prompt)

Unzip this folder into your existing project, allowing `app.py`, `requirements.txt`, and `assets/` to be replaced/added. Keep your existing `processed_data` folder.

Your project should look like:

```text
airline_flight_list_dashboard/
├── app.py
├── requirements.txt
├── assets/
│   └── tudelft_wordmark.svg
└── processed_data/
    ├── flights_processed.parquet
    ├── route_pairs.parquet
    ├── airport_summary.parquet
    ├── monthly_summary.parquet
    ├── preprocessing_report.json
    ├── unmatched_airports.csv
    └── validation_results.csv
```

In Anaconda Prompt:

```cmd
cd "C:\Users\Toni Manjani\Desktop\airline_flight_list_dashboard_full_year_map_fixed\airline_flight_list_dashboard"
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

If you do not have a virtual environment yet:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Important data notes

- The dashboard uses `flights_processed.parquet` for airline, aircraft, route, date and flight-level analysis. Make sure this file is copied from the notebook's `processed_data` output.
- The other three Parquet files provide route coordinates, airport dimensions and monthly reference data.
- The map uses airport coordinates and airport-to-airport network links. It does **not** show actual radar trajectories.
- `observation_span_min` is `last_seen - first_seen`. It is an observation-span proxy, not confirmed gate-to-gate or block time.
- Airport codes without a unique coordinate match remain available in traffic tables but are omitted from the map.

## Logo

The included SVG is a compact TU Delft-inspired dashboard wordmark, not the official corporate logo artwork and not an endorsement by TU Delft. If this dashboard is used in an official TU Delft publication, replace it with the approved logo downloaded from the [TU Delft Corporate Identity page](https://www.tudelft.nl/en/tu-delft-corporate-design) and follow its brand guidelines.
