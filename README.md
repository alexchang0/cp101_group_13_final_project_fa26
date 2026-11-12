# CYPLAN 101 final project

**Identifying Flood Risk Reduction from Marshes** — San Francisco Bay Area.

Research question: How does modeled wave attenuation vary across tidal marshes in the San Francisco Bay Area, and how do these patterns spatially relate to shoreline community vulnerability?

## Raw data downloads and required paths

Raw source data are excluded from Git. A fresh clone does not contain `data/raw/`; download the datasets below and arrange them at the configured paths before running the pipeline. Do not commit raw downloads.

Download the indicated releases and extract the geodatabases to these repository-relative paths.

| Dataset | Download source | Required geodatabase path |
|---|---|---|
| Baylands Habitat Map 2020 v1.3 | [SFEI / WRMP](https://www.sfei.org/data/baylands-habitat-map-2020-bhm-2020-version-13-gis-data) | `data/raw/BHM2020/BHM2020_v1_3/BHM2020_v1_3.gdb` |
| Baylands Resilience Metrics v1.2 | [SFEI](https://www.sfei.org/data/baylands-resilience-metrics) | `data/raw/Baylands_Resilience_Metrics_v1_2.gdb` |
| Community Vulnerability (BCDC 2020) | [CA Open Data](https://data.ca.gov/@san-francisco-bay-conservation-and-development-commission/community-vulnerability-bcdc-2020) | `data/raw/e221c89f-01bd-4e37-a742-31a7735df244.gdb` |
| SF Bay Shore Inventory (SFEI 2016) | [SFEI GIS data](https://www.sfei.org/data/sf-bay-shore-inventory-gis-data) | `data/raw/SFBayShoreInventory_SFEI_2016_0/ESRI ArcGIS/SFBayShoreInventory__SFEI_2016.gdb` |
| SF Bay Shore Inventory BHM2020 update | [SFEI GIS data](https://www.sfei.org/data/sf-bay-shore-inventory-gis-data) | `data/raw/SFEI_BayShoreInventory_BHM2020update_v1/SFEI_BayShoreInventory_BHM2020update_v1.gdb` |

Keep the Community Vulnerability geodatabase directory name as supplied; do not rename `e221c89f-01bd-4e37-a742-31a7735df244.gdb`. Click on "Download" -> "File Geodatabase".

## Install and run

The project uses Python 3.12. Run commands from the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/inspect_data.py
.venv/bin/python src/clean_data.py
.venv/bin/python src/map_tidal_marsh.py
.venv/bin/python src/plot_marsh_area_by_class.py
.venv/bin/python src/plot_shoreline_by_marsh_proximity.py
.venv/bin/python src/plot_wave_height_by_connectivity.py
```

## Workflow outputs

- `src/inspect_data.py` writes eight sample rows from each of the three raw datasets to `outputs/tables/data_inventory.json`.
- `src/clean_data.py` reads raw inputs and rebuilds GeoParquet files under `data/processed/`. It does not modify raw files.
- The plotting scripts create `outputs/figures/tidal_marsh_shoreline_map.png`, `outputs/figures/marsh_area_by_class.png`, `outputs/figures/shoreline_characteristics_by_marsh_proximity.png`, and `outputs/figures/wave_height_by_tidal_connectivity.png`.

## Scope and limitations

The charts describe mapped marsh area, modeled wave-height outputs across marsh connectivity classes, and shoreline characteristics near marshes. The wave-height chart compares the dataset's minimum and maximum output fields; it does not calculate wave-height reduction. The shoreline comparison uses a 100-meter buffer and an `intersects` join; it measures association, not marsh-caused flood reduction. The full population/equity and flood-exposure/protection-potential analyses are not yet implemented.
