#!/usr/bin/env python3
"""Compare resilience-metric wave-height outputs across marsh units."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/cleaned_baylands_resilience_metrics.gpkg"
LAYER = "analysis_units"
OUTPUT = ROOT / "outputs/figures/wave_height_by_tidal_connectivity.png"


def main() -> None:
    metrics = gpd.read_file(
        INPUT,
        layer=LAYER,
        engine="pyogrio",
        columns=[
            "Unit_Type",
            "Tidal_Connectivity",
            "MEAN_MIN_Output_Wave_Height",
            "MEAN_MAX_Output_Wave_Height",
        ],
    )

    marsh_units = metrics[metrics["Unit_Type"] == "Marsh Unit"].copy()
    marsh_units = marsh_units.dropna(subset=["Tidal_Connectivity"])
    summary = marsh_units.groupby("Tidal_Connectivity")[[
        "MEAN_MIN_Output_Wave_Height",
        "MEAN_MAX_Output_Wave_Height",
    ]].median()
    summary = summary.dropna(how="all").sort_index()

    positions = np.arange(len(summary))
    bar_height = 0.36
    color_min = "#79ad78"
    color_max = "#3d8b70"

    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.subplots_adjust(left=0.29, right=0.94, top=0.84, bottom=0.18)
    ax.barh(
        positions - bar_height / 2,
        summary["MEAN_MIN_Output_Wave_Height"],
        height=bar_height,
        color=color_min,
        label="Minimum Output",
    )
    ax.barh(
        positions + bar_height / 2,
        summary["MEAN_MAX_Output_Wave_Height"],
        height=bar_height,
        color=color_max,
        label="Maximum Output",
    )

    fig.text(0.29, 0.96, "Modeled Wave Height Outputs by Tidal Connectivity",
             ha="left", va="top", fontsize=16, fontweight="bold", color="#17324d")
    fig.text(0.29, 0.91, "Median values for Baylands Resilience Metrics marsh units",
             ha="left", va="top", fontsize=9.5, color="#526579")
    ax.set_yticks(positions, summary.index.astype(str))
    ax.set_xlabel("Wave Height (meters)")
    ax.set_ylabel("Tidal Connectivity")
    ax.grid(axis="x", color="#d5dfe5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, loc="lower right")
    ax.set_xlim(left=0)

    fig.text(0.29, 0.06,
             "Output wave heights are compared; wave-height reduction is not calculated here.",
             ha="left", fontsize=8.5, color="#526579")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=240, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"Chart written: {OUTPUT.relative_to(ROOT)}")
    print(f"Marsh units summarized: {len(marsh_units):,}")
    print(summary)


if __name__ == "__main__":
    main()
