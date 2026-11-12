#!/usr/bin/env python3
"""Compare updated shoreline inventory features by nearby BHM2020 marsh class."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
MARSH_FILE = ROOT / "data/processed/cleaned_bhm2020.parquet"
SHORE_FILE = ROOT / "data/processed/cleaned_shore_inventory_bhm2020_update.parquet"
OUTPUT = ROOT / "outputs/figures/shoreline_characteristics_by_marsh_proximity.png"
EXPECTED_EPSG = 26910
BUFFER_METERS = 100
CATEGORIES = ["High Marsh Only", "Low Marsh Only", "Both High and Low", "No Mapped Marsh"]


def read_layer(path: Path, columns: list[str]) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path, columns=["geometry"] + columns)


def main() -> None:
    marsh = read_layer(MARSH_FILE, ["Level4", "Level5"])
    shore = read_layer(SHORE_FILE, ["Segment_ID", "Fortified"])
    shore = shore.reset_index(drop=True)
    buffers = gpd.GeoDataFrame(
        {"shore_row": np.arange(len(shore), dtype="int64")},
        geometry=shore.geometry.buffer(BUFFER_METERS), crs=shore.crs,
    )
    joined = gpd.sjoin(
        buffers, marsh[["Level5", "geometry"]], how="left", predicate="intersects"
    )
    matches = joined.loc[joined["Level5"].notna(), ["shore_row", "Level5"]]
    matched_segments = matches["shore_row"].nunique()
    classes_by_row = matches.groupby("shore_row")["Level5"].agg(set)

    def category_for(row: int) -> str:
        classes = classes_by_row.get(row, set())
        has_high = "High Marsh" in classes
        has_low = "Low Marsh" in classes
        if has_high and has_low:
            return "Both High and Low"
        if has_high:
            return "High Marsh Only"
        if has_low:
            return "Low Marsh Only"
        return "No Mapped Marsh"

    shore["marsh_proximity"] = [category_for(row) for row in range(len(shore))]
    shore["length_km"] = shore.geometry.length / 1000.0
    fortified = shore["Fortified"].astype("string").str.strip().str.casefold()
    shore["fortified_status"] = fortified.map({"yes": "Yes", "no": "No"})

    lengths = shore.groupby("marsh_proximity")["length_km"].sum().reindex(CATEGORIES, fill_value=0)
    counts = shore.groupby("marsh_proximity").size().reindex(CATEGORIES, fill_value=0)
    status_lengths = shore.groupby(["marsh_proximity", "fortified_status"], dropna=False)["length_km"].sum()
    fortified_km = status_lengths.xs("Yes", level="fortified_status").reindex(CATEGORIES, fill_value=0)
    known_km = (
        status_lengths.xs("Yes", level="fortified_status").reindex(CATEGORIES, fill_value=0)
        + status_lengths.xs("No", level="fortified_status").reindex(CATEGORIES, fill_value=0)
    )
    fortified_share = (fortified_km / known_km).where(known_km > 0)
    known_share = (known_km / lengths).where(lengths > 0)

    y_labels = CATEGORIES[::-1]
    bar_color = "#3d8b70"
    fig, (ax_len, ax_fort) = plt.subplots(1, 2, figsize=(15, 7.5), sharey=True)
    fig.subplots_adjust(left=0.22, right=0.97, bottom=0.19, top=0.82, wspace=0.35)
    fig.text(0.22, 0.96, "Shoreline Characteristics by Nearby Tidal Marsh",
             ha="left", va="top", fontsize=17, fontweight="bold", color="#17324d")
    fig.text(0.22, 0.915,
             f"100 m Shoreline Buffers Joined to BHM2020 Marsh Polygons Using Intersects "
             f"(EPSG:{EXPECTED_EPSG})",
             ha="left", va="top", fontsize=10, color="#526579")

    y = np.arange(len(y_labels))
    ax_len.barh(y, lengths.reindex(y_labels).values, color=bar_color, height=0.66)
    ax_len.set_yticks(y, y_labels)
    ax_len.set_title("Total Shoreline Length", loc="left", fontsize=12, color="#17324d", pad=12)
    ax_len.set_xlabel("Shoreline Segment Length (km)")
    ax_len.xaxis.grid(True, color="#d5dfe5", linewidth=0.8)
    ax_len.set_axisbelow(True)
    ax_len.spines[["top", "right", "left"]].set_visible(False)
    ax_len.tick_params(axis="y", length=0)
    max_length = max(float(lengths.max()), 1.0)
    ax_len.set_xlim(0, max_length * 1.4)
    for ypos, label in zip(y, y_labels):
        value = lengths[label]
        ax_len.text(value + max_length * 0.025, ypos,
                    f"{value:,.1f} km  ·  {counts[label]:,} Shoreline Segments",
                    va="center", ha="left", fontsize=8.5, color="#17324d")

    share_values = fortified_share.reindex(y_labels)
    plot_share = share_values.fillna(0)
    ax_fort.barh(y, plot_share.values, color=bar_color, height=0.66)
    ax_fort.set_yticks(y, y_labels)
    ax_fort.tick_params(axis="y", labelleft=False, length=0)
    ax_fort.set_title("Length-Weighted Fortified Share", loc="left", fontsize=12,
                      color="#17324d", pad=12)
    ax_fort.set_xlabel("Fortified Share of Known-Status Shoreline Length")
    ax_fort.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax_fort.set_xticks(np.linspace(0, 1, 6))
    ax_fort.xaxis.grid(True, color="#d5dfe5", linewidth=0.8)
    ax_fort.set_axisbelow(True)
    ax_fort.spines[["top", "right", "left"]].set_visible(False)
    ax_fort.set_xlim(0, 1.0)
    for ypos, label in zip(y, y_labels):
        share = fortified_share[label]
        coverage = known_share[label]
        if pd.isna(share):
            text = "No Known Status"
        else:
            text = f"{share:.0%} Fortified  ·  {coverage:.1%} Status Known"
        ax_fort.text((0 if pd.isna(share) else share) + 0.025, ypos, text,
                     va="center", ha="left", fontsize=8.2, color="#17324d")

    fig.text(0.22, 0.085,
             "Fortified Share = Yes Length / (Yes + No Length).",
             ha="left", va="top", fontsize=8.5, color="#526579")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=220, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(f"Chart written: {OUTPUT.relative_to(ROOT)}")
    print(f"Spatial join: {len(shore):,} shoreline segments; buffer={BUFFER_METERS} m; "
          f"predicate=intersects; matched shoreline segments={matched_segments:,}")
    for label in CATEGORIES:
        share_text = "n/a" if pd.isna(fortified_share[label]) else f"{fortified_share[label]:.1%}"
        print(f"- {label}: {counts[label]:,} shoreline segments, {lengths[label]:,.2f} km, "
              f"fortified length share={share_text}, known-status length={known_share[label]:.1%}")


if __name__ == "__main__":
    main()
