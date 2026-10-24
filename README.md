# Shifting Grounds

Shifting Grounds trains one habitat model per species on NOAA's fall bottom trawl
survey, using bottom temperature and depth. It re-predicts habitat on a grid under
+1°C and +2°C warming, measures how habitat inside each active offshore wind lease
changes, and labels the change as a planning signal. A Streamlit app shows the map,
the signals, NOAA revenue context, a hindcast check, and plain-English briefs.

This tool shows **change in fishing overlap, not harm to fish**, and is a planning
signal rather than a build or don't-build verdict.

## Setup

1. Create and activate a virtual environment (Python 3.10+):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your DeepSeek API key:
   ```bash
   cp .env.example .env
   # then edit .env and set DEEPSEEK_API_KEY=...
   ```
   `DEEPSEEK_MODEL` defaults to `deepseek-chat`.

## Download the data

The raw data is not committed (`data/raw/` is gitignored). Download it into the
folders below before running the pipeline.

### 1. NOAA NEFSC fall bottom trawl survey → `data/raw/survey/`

Per tow: location, depth, bottom temperature and salinity; catch weight and count
by species. See [InPort item 22560](https://www.fisheries.noaa.gov/inport/item/22560).

- Survey data zip:
  `https://storage.googleapis.com/nmfs_odp_nefsc/PARR/PEMAD/ESB/22560/22560_NEFSCFallFisheriesIndependentBottomTrawlData.zip`
- Code/support tables:
  `https://storage.googleapis.com/nmfs_odp_nefsc/PARR/PEMAD/ESB/SVDBS/SVDBS_SupportTables.zip`

Unzip both into `data/raw/survey/`.

### 2. BOEM lease areas → `data/raw/boem/`

Wind lease area boundaries (shapefile or geodatabase). Download from
[BOEM Renewable Energy GIS Data](https://www.boem.gov/Renewable-Energy-GIS-Data/)
and place the shapefile into `data/raw/boem/`.

### 3. NOAA wind area landings and value → `data/raw/revenue/`

Landings and value per lease or project area by species, gear and port, 2008–2025.
Export the CSV (species view, all areas) from the
[NOAA GARFO data tool](https://apps-garfo.fisheries.noaa.gov/offshore-energy/wind-reports/ALL_WEA_BY_AREA_DATA.html)
and place it in `data/raw/revenue/`.

## Run

Build the processed files, then launch the app:

```bash
python src/prepare_data.py
python src/train.py
python src/hindcast.py
python src/scenarios.py
python src/overlap.py
streamlit run app.py
```

## Project structure

```text
shifting-grounds/
├── app.py                 # Streamlit app: map, selectors, lease panel, hindcast
├── src/                   # prepare_data, train, hindcast, scenarios, overlap, explain
├── data/
│   ├── raw/               # gitignored: survey/, boem/, revenue/
│   └── processed/         # tows.csv, presence.csv, grid_predictions.csv, lease_signals.csv, hindcast.csv
├── models/                # <species>.joblib, metrics.json
├── docs/                  # DECISIONS.md, CHANGELOG.md, WRITEUP.md, DEMO.md
├── requirements.txt
├── .env.example
└── README.md
```

## Data credits

- **Survey data:** NOAA Fisheries, Northeast Fisheries Science Center bottom trawl survey.
- **Lease areas:** Bureau of Ocean Energy Management.
- **Fishing revenue:** NOAA Fisheries, Greater Atlantic Regional Fisheries Office.
