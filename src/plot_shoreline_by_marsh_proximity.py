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
from pyproj import CRS


ROOT = Path(__file__).resolve().parents[1]
MARSH_FILE = ROOT / "data/processed/cleaned_bhm2020.gpkg"
MARSH_LAYER = "tidal_marsh"
SHORE_FILE = ROOT / "data/processed/cleaned_shore_inventory_bhm2020_update.gpkg"
SHORE_LAYER = "shore_inventory_update"
OUTPUT = ROOT / "outputs/figures/shoreline_characteristics_by_marsh_proximity.png"
EXPECTED_EPSG = 26910
BUFFER_METERS = 100
CATEGORIES = ["High marsh only", "Low marsh only", "Both high and low", "No mapped marsh"]


def read_layer(path: Path, layer: str, columns: list[str]) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing cleaned input: {path.relative_to(ROOT)}")
    frame = gpd.read_file(path, layer=layer, engine="pyogrio", columns=columns)
    epsg = CRS.from_user_input(frame.crs).to_epsg() if frame.crs else None
    if epsg != EXPECTED_EPSG:
        raise ValueError(f"{path.relative_to(ROOT)}::{layer} must have EPSG:{EXPECTED_EPSG}; found {frame.crs!s}")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"{path.relative_to(ROOT)}::{layer} contains null or empty geometries")
    if not frame.geometry.is_valid.all():
        raise ValueError(f"{path.relative_to(ROOT)}::{layer} contains invalid geometries")
    return frame


def main() -> None:
    marsh = read_layer(MARSH_FILE, MARSH_LAYER, ["Level4", "Level5"])
    shore = read_layer(SHORE_FILE, SHORE_LAYER, ["Segment_ID", "Fortified"])
    if not marsh["Level4"].eq("Tidal Marsh").all():
        raise ValueError("BHM input includes features outside Level4 == 'Tidal Marsh'")
    observed_classes = set(marsh["Level5"].dropna().astype(str).unique())
    expected_classes = {"High Marsh", "Low Marsh"}
    if observed_classes != expected_classes or marsh["Level5"].isna().any():
        raise ValueError(f"Unexpected or missing BHM Level5 classes: {sorted(observed_classes)}")
    if "Fortified" not in shore:
        raise ValueError("Shoreline inventory is missing the required Fortified field")

    # Each source feature is its own analysis unit. Segment_ID is retained for
    # traceability but repeated IDs are not merged or dropped.
    shore = shore.reset_index(drop=True)
    buffers = gpd.GeoDataFrame(
        {"shore_row": np.arange(len(shore), dtype="int64")},
        geometry=shore.geometry.buffer(BUFFER_METERS), crs=shore.crs,
    )
    joined = gpd.sjoin(
        buffers, marsh[["Level5", "geometry"]], how="left", predicate="intersects"
    )
    matches = joined.loc[joined["Level5"].notna(), ["shore_row", "Level5"]]
    classes_by_row = matches.groupby("shore_row")["Level5"].agg(set)

    def category_for(row: int) -> str:
        classes = classes_by_row.get(row, set())
        has_high = "High Marsh" in classes
        has_low = "Low Marsh" in classes
        if has_high and has_low:
            return "Both high and low"
        if has_high:
            return "High marsh only"
        if has_low:
            return "Low marsh only"
        return "No mapped marsh"

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
    unknown_status_rows = int(shore["fortified_status"].isna().sum())
    unknown_status_length = float(shore.loc[shore["fortified_status"].isna(), "length_km"].sum())

    y_labels = CATEGORIES[::-1]
    bar_color = "#3d8b70"
    fig, (ax_len, ax_fort) = plt.subplots(1, 2, figsize=(13, 7.5), sharey=True)
    fig.subplots_adjust(left=0.22, right=0.97, bottom=0.19, top=0.82, wspace=0.12)
    fig.text(0.22, 0.96, "Shoreline characteristics by nearby tidal marsh",
             ha="left", va="top", fontsize=17, fontweight="bold", color="#17324d")
    fig.text(0.22, 0.915,
             f"100 m shoreline buffers joined to BHM2020 marsh polygons using intersects "
             f"(EPSG:{EXPECTED_EPSG})",
             ha="left", va="top", fontsize=10, color="#526579")

    y = np.arange(len(y_labels))
    ax_len.barh(y, lengths.reindex(y_labels).values, color=bar_color, height=0.66)
    ax_len.set_yticks(y, y_labels)
    ax_len.set_title("Total shoreline length", loc="left", fontsize=12, color="#17324d", pad=12)
    ax_len.set_xlabel("Shoreline feature length (km)")
    ax_len.xaxis.grid(True, color="#d5dfe5", linewidth=0.8)
    ax_len.set_axisbelow(True)
    ax_len.spines[["top", "right", "left"]].set_visible(False)
    ax_len.tick_params(axis="y", length=0)
    max_length = max(float(lengths.max()), 1.0)
    ax_len.set_xlim(0, max_length * 1.4)
    for ypos, label in zip(y, y_labels):
        value = lengths[label]
        ax_len.text(value + max_length * 0.025, ypos,
                    f"{value:,.1f} km  ·  {counts[label]:,} features",
                    va="center", ha="left", fontsize=8.5, color="#17324d")

    share_values = fortified_share.reindex(y_labels)
    plot_share = share_values.fillna(0)
    ax_fort.barh(y, plot_share.values, color=bar_color, height=0.66)
    ax_fort.set_yticks(y, y_labels)
    ax_fort.tick_params(axis="y", labelleft=False, length=0)
    ax_fort.set_title("Length-weighted fortified share", loc="left", fontsize=12,
                      color="#17324d", pad=12)
    ax_fort.set_xlabel("Fortified share of known-status shoreline length")
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
            text = "No known status"
        else:
            text = f"{share:.0%} fortified  ·  {coverage:.0%} length known"
        ax_fort.text((0 if pd.isna(share) else share) + 0.025, ypos, text,
                     va="center", ha="left", fontsize=8.2, color="#17324d")

    fig.text(0.22, 0.085,
             f"Fortified share = Yes length / (Yes + No length); blank status excluded. "
             f"Blank status overall: {unknown_status_rows:,} features ({unknown_status_length:,.1f} km). "
             "Rows represent inventory features; repeated Segment_IDs are not merged.",
             ha="left", va="top", fontsize=8.5, color="#526579", wrap=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=220, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(f"Chart written: {OUTPUT.relative_to(ROOT)}")
    print(f"Spatial join: {len(shore):,} shoreline features; buffer={BUFFER_METERS} m; "
          f"predicate=intersects; matched feature rows={len(matches):,}")
    print(f"Fortified status blank/unrecognized: {unknown_status_rows:,} features, "
          f"{unknown_status_length:,.2f} km (excluded from fortified-share denominator)")
    for label in CATEGORIES:
        share_text = "n/a" if pd.isna(fortified_share[label]) else f"{fortified_share[label]:.1%}"
        print(f"- {label}: {counts[label]:,} features, {lengths[label]:,.2f} km, "
              f"fortified length share={share_text}, known-status length={known_share[label]:.1%}")


if __name__ == "__main__":
    main()
