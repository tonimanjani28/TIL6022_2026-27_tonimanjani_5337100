# Air Traffic Analysis for the European Union members in 2025

**TIL6022 TIL Programming Final Project**
**Author: Toni Manjani**

## Project overview

This project investigates patterns in observed air traffic activity during 2025 using the **Open Performance Data Initiative (OPDI) Flight List**, developed by EUROCONTROL's Performance Review Commission in collaboration with the OpenSky Network. It combines data preparation, descriptive analysis and an interactive **Streamlit dashboard**.

The research explores how flight list records are distributed over time, among airlines/operators and aircraft types, and across airports and directional routes. The dashboard makes it possible to explore these patterns using interactive filters, charts, tables and a map of airport connections.

## Research goal

**The goal is to describe the distribution and structure of observed flight activity in 2025, while examining how data completeness affects the interpretation of airport and route-network results.**

The research focuses on five questions:

1. How does recorded flight activity vary across the months of 2025?
2. Which operators and aircraft types are most represented in the dataset?
3. Which airports have the highest recorded departure and arrival activity?
4. Which directional airport pairs are most frequent, and what does the observed network look like?
5. How do missing airport codes and incomplete records limit these analyses?

The study is descriptive. The records are derived from surveillance data and should not be treated as a complete census of flights. The network map connects airport locations; its lines are **not actual flown trajectories**. The available flight list data does not establish scheduled delays or on time performance.

## Dashboard features

The Streamlit app includes an activity overview, interactive airport-pair network map, airline/operator comparisons, airport departure and arrival summaries, aircraft fleet views, directional route rankings, a searchable flight explorer with CSV export, and a data-quality view. Filters allow exploration by date, operator, airport and aircraft type.

## Requirements

- Python 3.10 or newer (Python 3.11 is a reasonable choice)
- Git (or download the repository as a ZIP file)
- The four **processed Parquet datasets** described below

The repository includes `requirements.txt` for installing the Python libraries used by the app.

## 1. Download the project

Open a terminal and clone the repository:

```bash
git clone https://github.com/tonimanjani28/TIL6022_2026-27_tonimanjani_5337100.git
cd TIL6022_2026-27_tonimanjani_5337100
```

Alternatively, select **Code>Download ZIP** on GitHub, extract it and open a terminal inside the extracted project folder.

## 2. Install dependencies

### Windows (PowerShell)

Run the following commands from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, you can use the environment's Python directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### macOS (Terminal)

Run the following commands from the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Using a virtual environment helps keep the project's dependencies separate from other Python installations.

## 3. Add the processed datasets

**The dashboard cannot display its analyses without the prepared data files.** Create a folder named `processed_data` beside `app.py` and place these four files inside it:

```text
TIL6022_2026-27_tonimanjani_5337100/
├── app.py
├── requirements.txt
├── README.md
└── processed_data/
    ├── flights_processed.parquet
    ├── route_pairs.parquet
    ├── airport_summary.parquet
    └── monthly_summary.parquet
```

These are **processed outputs**, not the original monthly downloads. If you already have the four files from the preprocessing notebook, copy them into this folder. Otherwise, obtain the original monthly Flight List files from the [OPDI Flight List download page](https://www.opdi.aero/flight-list-data), prepare the airport reference data, and run the preprocessing notebook to generate the outputs. The repository currently includes `flight_data_preprocessing_and_route_pairs.ipynb`; the expanded research report notebook will be added separately.

Optional supporting files in `processed_data` include `preprocessing_report.json`, `unmatched_airports.csv` and `validation_results.csv`, which support the data-quality view.

## 4. Run the Streamlit app

### Windows

With the virtual environment activated, run:

```powershell
python -m streamlit run app.py
```

If you did not activate it, run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS

With the virtual environment activated, run:

```bash
python -m streamlit run app.py
```

Streamlit will normally open the dashboard in your browser at **http://localhost:8501**. To stop the app, return to the terminal and press **Ctrl+C**.

## Troubleshooting

- **Missing processed datasets:** Check that the four required `.parquet` files are in `processed_data/`, directly beside `app.py`, with the exact filenames shown above.
- **`No module named streamlit`:** Install dependencies in the same Python environment used to launch the app: `python -m pip install -r requirements.txt`.
- **`numpy.core.multiarray failed to import`:** This usually indicates incompatible or damaged Python packages. Create a fresh virtual environment and reinstall the dependencies using the instructions above.
- **Port already in use:** Run `python -m streamlit run app.py --server.port 8502` and open http://localhost:8502.

## Data and sources

- [OPDI — Flight List dataset](https://www.opdi.aero/flight-list-data)
- [OPDI — Data catalogue](https://www.opdi.aero/data)
- [OPDI — Concepts and definitions](https://www.opdi.aero/concepts)
- [OurAirports — Airport reference data](https://ourairports.com/data/)

The research notebook documents the preparation decisions, indicator definitions, limitations and empirical findings in more detail.
