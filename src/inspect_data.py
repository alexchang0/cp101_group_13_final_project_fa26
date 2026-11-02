#!/usr/bin/env python3
"""Write eight sample rows from each raw project dataset."""

import json
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "outputs" / "tables" / "data_inventory.json"
SAMPLE_SIZE = 8


def main():
    metrics = gpd.read_file(
        RAW / "Baylands_Resilience_Metrics_v1_2.gdb",
        layer="Analysis_Units_2020_v1_2",
        engine="pyogrio",
        rows=SAMPLE_SIZE,
        ignore_geometry=True,
    )
    metrics_rows = json.loads(
        metrics.head(SAMPLE_SIZE).to_json(orient="records", date_format="iso")
    )

    marsh = gpd.read_file(
        RAW / "BHM2020" / "BHM2020_v1_3" / "BHM2020_v1_3.gdb",
        layer="BaylandsHabitatMap2020_v1_3",
        engine="pyogrio",
        rows=SAMPLE_SIZE,
        ignore_geometry=True,
    )
    marsh_rows = json.loads(
        marsh.head(SAMPLE_SIZE).to_json(orient="records", date_format="iso")
    )

    shore = gpd.read_file(
        RAW / "SFEI_BayShoreInventory_BHM2020update_v1" / "SFEI_BayShoreInventory_BHM2020update_v1.gdb",
        layer="SFEI_BayShoreInventory_BHM2020update_v1",
        engine="pyogrio",
        rows=SAMPLE_SIZE,
        ignore_geometry=True,
    )
    shore_rows = json.loads(
        shore.head(SAMPLE_SIZE).to_json(orient="records", date_format="iso")
    )

    inventory = {
        "sample_size": SAMPLE_SIZE,
        "datasets": [
            {
                "name": "Baylands Resilience Metrics",
                "path": "data/raw/Baylands_Resilience_Metrics_v1_2.gdb",
                "layer": "Analysis_Units_2020_v1_2",
                "sample_rows": metrics_rows,
            },
            {
                "name": "BHM 2020 tidal marsh",
                "path": "data/raw/BHM2020/BHM2020_v1_3/BHM2020_v1_3.gdb",
                "layer": "BaylandsHabitatMap2020_v1_3",
                "sample_rows": marsh_rows,
            },
            {
                "name": "Shore Inventory BHM 2020 Update",
                "path": "data/raw/SFEI_BayShoreInventory_BHM2020update_v1/SFEI_BayShoreInventory_BHM2020update_v1.gdb",
                "layer": "SFEI_BayShoreInventory_BHM2020update_v1",
                "sample_rows": shore_rows,
            },
        ],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
