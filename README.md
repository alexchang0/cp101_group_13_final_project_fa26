# CYPLAN 101 final project

**Identifying Flood Risk Reduction from Marshes** — San Francisco Bay Area.

Research question: To what extent are existing tidal marshes associated with coastal flood exposure for Bay Area communities, and how is estimated marsh-related flood protection potential distributed across populations and Equity Priority Communities?

## Setup and run

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/inspect_data.py
.venv/bin/python src/clean_data.py
```

`inspect_data.py` reads `data/raw/` and writes metadata and sample records to `outputs/tables/data_inventory.json`. `clean_data.py` reads the original raw datasets and writes rebuildable GeoPackages under `data/processed/`. Neither script modifies raw data. The research analysis pipeline has not been implemented yet.

## Raw data sources

Raw datasets stay local under `data/raw/` and are excluded from Git by `.gitignore`. Download the versions listed below from their source pages, preserving the supplied filenames and directory structure. The existing local copies are already available; do not redownload them unless needed.

| Local dataset | Source / download |
|---|---|
| Baylands Habitat Map 2020 v1.3 | [SFEI / WRMP download page](https://www.sfei.org/data/baylands-habitat-map-2020-bhm-2020-version-13-gis-data) |
| Baylands Resilience Metrics v1.2 | [SFEI download page](https://www.sfei.org/data/baylands-resilience-metrics) |
| SFEI Shore Inventory 2016 and BHM2020 update | [SFEI GIS data page](https://www.sfei.org/data/sf-bay-shore-inventory-gis-data) |
| BCDC Community Vulnerability / Flood Explorer materials | [BCDC Community Vulnerability mapping and downloads](https://www.bcdc.ca.gov/resources/maps-and-data/community-vulnerability-mapping/); use the 2020 vintage matching the project data |

Some packages include both compressed and extracted copies. Keep one working copy where possible; do not commit either copy to Git.

## Project paths

- Raw source data (local only): `data/raw/`
- Python scripts: `src/`
- Data reference: `docs/data_dictionary.md`
- Inspection results: `outputs/tables/data_inventory.json`
