#!/usr/bin/env python3
"""Plot cleaned BHM2020 tidal marsh area by its observed Level5 class."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyproj import CRS


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/cleaned_bhm2020.gpkg"
LAYER = "tidal_marsh"
OUTPUT = ROOT / "outputs/figures/marsh_area_by_class.png"
EXPECTED_EPSG = 26910


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(f"Missing cleaned input: {INPUT.relative_to(ROOT)}")
    marsh = gpd.read_file(INPUT, layer=LAYER, engine="pyogrio",
                          columns=["Level4", "Level5"])
    epsg = CRS.from_user_input(marsh.crs).to_epsg() if marsh.crs else None
    if epsg != EXPECTED_EPSG:
        raise ValueError(f"Expected EPSG:{EXPECTED_EPSG}; found {marsh.crs!s}")
    if not marsh["Level4"].eq("Tidal Marsh").all():
        raise ValueError("Input layer contains features outside Level4 == 'Tidal Marsh'")
    if marsh.geometry.isna().any() or marsh.geometry.is_empty.any():
        raise ValueError("Input layer contains null or empty geometries")
    if not marsh.geometry.is_valid.all():
        raise ValueError("Input layer contains invalid geometries")

    # EPSG:26910 uses metres, so geometry.area returns square metres.
    marsh["area_km2"] = marsh.geometry.area / 1_000_000
    marsh["Level5"] = marsh["Level5"].fillna("Missing / unclassified")
    summary = marsh.groupby("Level5", dropna=False)["area_km2"].sum().sort_values()
    if summary.empty:
        raise ValueError("No habitat classes found to chart")

    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.subplots_adjust(left=0.24, right=0.93, top=0.87, bottom=0.19)
    color = "#39866f"
    bars = ax.barh(summary.index.astype(str), summary.values, color=color, height=0.62)
    fig.text(0.24, 0.98, "Tidal marsh area by habitat class", ha="left", va="top",
             fontsize=16, fontweight="bold", color="#17324d")
    fig.text(0.24, 0.91, "BHM2020 Level5 labels within the cleaned Level4 tidal-marsh layer",
             ha="left", va="top", fontsize=9.5, color="#526579")
    ax.set_xlabel("Area (square kilometers)")
    ax.set_ylabel("BHM2020 Level5 class")
    ax.grid(axis="x", color="#d5dfe5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#9aabb6")
    ax.tick_params(axis="y", length=0, labelsize=10)
    ax.tick_params(axis="x", colors="#526579")
    ax.set_xlim(0, max(summary.values) * 1.18)
    for bar, value in zip(bars, summary.values):
        ax.text(value + max(summary.values) * 0.015,
                bar.get_y() + bar.get_height() / 2,
                f"{value:,.1f} km²", va="center", ha="left",
                fontsize=10, color="#17324d")
    fig.text(0.24, 0.07,
             f"Area calculated from cleaned polygon geometry in EPSG:{EXPECTED_EPSG}; "
             f"{len(marsh):,} tidal-marsh polygons. Class labels are shown as stored.",
             ha="left", fontsize=8.5, color="#526579")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=240, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"Chart written: {OUTPUT.relative_to(ROOT)}")
    print(f"Features summarized: {len(marsh):,}; CRS: EPSG:{EXPECTED_EPSG}")
    for label, area in summary.sort_values(ascending=False).items():
        print(f"- {label}: {area:,.3f} km²")


if __name__ == "__main__":
    main()
