#!/usr/bin/env python3
"""Map cleaned BHM2020 tidal marsh polygons against the updated bay shoreline."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
from matplotlib.ticker import FuncFormatter, MultipleLocator
from pyproj import CRS
import shapely


ROOT = Path(__file__).resolve().parents[1]
MARSH_FILE = ROOT / "data/processed/cleaned_bhm2020.gpkg"
MARSH_LAYER = "tidal_marsh"
SHORE_FILE = ROOT / "data/processed/cleaned_shore_inventory_bhm2020_update.gpkg"
SHORE_LAYER = "shore_inventory_update"
OUTPUT = ROOT / "outputs/figures/tidal_marsh_shoreline_map.png"
EXPECTED_EPSG = 26910
DISPLAY_SIMPLIFY_METERS = 20.0


def read_layer(path: Path, layer: str) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing cleaned input: {path.relative_to(ROOT)}")
    frame = gpd.read_file(path, layer=layer, engine="pyogrio", columns=[])
    epsg = CRS.from_user_input(frame.crs).to_epsg() if frame.crs else None
    if epsg != EXPECTED_EPSG:
        raise ValueError(
            f"{path.relative_to(ROOT)}::{layer} must have verified EPSG:{EXPECTED_EPSG}; "
            f"found {frame.crs!s}"
        )
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"{path.relative_to(ROOT)}::{layer} has null or empty geometries")
    return frame


def compound_path(geometries, polygonal: bool) -> MplPath:
    """Create one Matplotlib path for many simplified polygon/line features."""
    vertex_parts = []
    code_parts = []

    def add_ring(coords, closed: bool) -> None:
        vertices = np.asarray(coords, dtype="float64")[:, :2]
        codes = np.full(len(vertices), MplPath.LINETO, dtype="uint8")
        codes[0] = MplPath.MOVETO
        if closed:
            codes[-1] = MplPath.CLOSEPOLY
        vertex_parts.append(vertices)
        code_parts.append(codes)

    for geometry in geometries:
        parts = geometry.geoms if geometry.geom_type.startswith("Multi") else [geometry]
        for part in parts:
            if polygonal:
                add_ring(part.exterior.coords, closed=True)
                for interior in part.interiors:
                    add_ring(interior.coords, closed=True)
            else:
                add_ring(part.coords, closed=False)

    return MplPath(np.concatenate(vertex_parts), np.concatenate(code_parts))


def main() -> None:
    marsh = read_layer(MARSH_FILE, MARSH_LAYER)
    shore = read_layer(SHORE_FILE, SHORE_LAYER)
    if not marsh.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("The tidal_marsh layer contains non-polygon geometries")
    if not shore.geom_type.isin(["LineString", "MultiLineString"]).all():
        raise ValueError("The shoreline update layer contains non-line geometries")

    min_x = min(marsh.total_bounds[0], shore.total_bounds[0])
    min_y = min(marsh.total_bounds[1], shore.total_bounds[1])
    max_x = max(marsh.total_bounds[2], shore.total_bounds[2])
    max_y = max(marsh.total_bounds[3], shore.total_bounds[3])
    margin_x = (max_x - min_x) * 0.025
    margin_y = (max_y - min_y) * 0.02
    bounds = (min_x - margin_x, min_y - margin_y,
              max_x + margin_x, max_y + margin_y)

    # Simplification is only for display; the cleaned GeoPackages are unchanged.
    marsh_display = shapely.simplify(marsh.geometry.array, DISPLAY_SIMPLIFY_METERS,
                                    preserve_topology=True)
    shore_display = shapely.simplify(shore.geometry.array, DISPLAY_SIMPLIFY_METERS,
                                    preserve_topology=True)
    marsh_path = compound_path(marsh_display, polygonal=True)
    shore_path = compound_path(shore_display, polygonal=False)

    fig, ax = plt.subplots(figsize=(9, 13))
    fig.subplots_adjust(left=0.12, right=0.97, bottom=0.065, top=0.90)
    fig.text(0.12, 0.975, "Tidal marshes along the San Francisco Bay shoreline",
             ha="left", va="top", fontsize=16, fontweight="bold", color="#17324d")
    fig.text(0.12, 0.951,
             "BHM2020 marsh polygons • SFEI Bay Shore Inventory update • "
             f"NAD83 / UTM Zone 10N (EPSG:{EXPECTED_EPSG}) • display simplified by "
             f"{DISPLAY_SIMPLIFY_METERS:g} m",
             ha="left", va="top", fontsize=9, color="#526579")
    ax.set_facecolor("#f5f8fa")
    ax.add_patch(PathPatch(marsh_path, facecolor="#79ad78", edgecolor="#477a58",
                           linewidth=0.12, zorder=2))
    ax.add_patch(PathPatch(shore_path, facecolor="none", edgecolor="#17324d",
                           linewidth=0.55, zorder=3))

    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal", adjustable="box")
    ax.xaxis.set_major_locator(MultipleLocator(10_000))
    ax.yaxis.set_major_locator(MultipleLocator(10_000))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}"))
    ax.grid(color="#cbd6de", linewidth=0.55, linestyle=(0, (3, 4)), zorder=1)
    ax.set_xlabel("UTM easting (km)")
    ax.set_ylabel("UTM northing (km)")
    legend = [
        Patch(facecolor="#79ad78", edgecolor="#477a58", label="Tidal marsh (BHM2020)"),
        Line2D([0], [0], color="#17324d", linewidth=1.5,
               label="Bay shoreline (SFEI update)"),
    ]
    ax.legend(handles=legend, loc="lower left", frameon=True, framealpha=0.95)
    ax.text(1, 0, f"{len(marsh):,} marsh polygons  •  {len(shore):,} shoreline features",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color="#526579")
    ax.annotate("N", xy=(0.94, 0.94), xytext=(0.94, 0.875), xycoords="axes fraction",
                ha="center", va="center", fontsize=10, fontweight="bold",
                arrowprops={"arrowstyle": "-|>", "color": "#17324d", "lw": 1.2})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=240, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"Map written: {OUTPUT.relative_to(ROOT)}")
    print(f"Tidal marsh: {len(marsh):,} polygons; shoreline: {len(shore):,} features")
    print(f"CRS: EPSG:{EXPECTED_EPSG}; display simplification: {DISPLAY_SIMPLIFY_METERS:g} m")


if __name__ == "__main__":
    main()
