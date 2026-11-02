#!/usr/bin/env python3
"""Clean the Baylands Resilience Metrics, BHM2020, and updated shoreline data."""

from pathlib import Path

import geopandas as gpd
import pandas as pd


def main():
    # Set up file paths
    project_folder = Path(__file__).resolve().parents[1]
    raw_folder = project_folder / "data" / "raw"
    processed_folder = project_folder / "data" / "processed"
    processed_folder.mkdir(parents=True, exist_ok=True)
    target_crs = "EPSG:26910"

    # Clean Baylands Resilience Metrics
    print("Baylands Resilience Metrics")
    metrics_file = raw_folder / "Baylands_Resilience_Metrics_v1_2.gdb"
    metrics = gpd.read_file(
        metrics_file,
        layer="Analysis_Units_2020_v1_2",
        engine="pyogrio",
    )

    metrics_rows_before = len(metrics)
    print("Raw shape:", metrics.shape)
    print("Raw columns:", metrics.columns.tolist())
    print("Raw CRS:", metrics.crs)
    print("Unit types:")
    print(metrics["Unit_Type"].value_counts(dropna=False))
    print("Missing values in key fields:")
    print(metrics[[
        "Unit_Type",
        "OLU_ID",
        "Tidal_Connectivity",
        "MEAN_RANGE_Marsh_Width",
        "MEAN_MIN_Output_Wave_Height",
        "MEAN_MAX_Output_Wave_Height",
    ]].isna().sum())

    metrics = metrics.dropna(subset=["geometry"]).copy()
    metrics = metrics[~metrics.geometry.is_empty].copy()

    metrics_invalid = metrics.loc[~metrics.geometry.is_valid].copy()
    metrics_valid = metrics.loc[metrics.geometry.is_valid].copy()
    if len(metrics_invalid) > 0:
        metrics_invalid["_source_row"] = metrics_invalid.index
        metrics_invalid.geometry = metrics_invalid.geometry.make_valid(
            method="structure", keep_collapsed=False
        )
        metrics_invalid = metrics_invalid.explode(index_parts=False)
        metrics_invalid = metrics_invalid[
            metrics_invalid.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        ]
        metrics_invalid = metrics_invalid.dissolve(
            by="_source_row", aggfunc="first"
        ).reset_index()
        metrics_invalid = metrics_invalid.drop(columns=["_source_row"])
        metrics = pd.concat([metrics_valid, metrics_invalid])
        metrics = gpd.GeoDataFrame(metrics, geometry="geometry", crs=metrics_valid.crs)

    metrics = metrics.reset_index(drop=True)
    metrics = metrics.drop_duplicates().copy()

    if metrics.crs is not None and metrics.crs.to_epsg() is not None:
        metrics = metrics.to_crs(target_crs)

    print("Rows before cleaning:", metrics_rows_before)
    print("Rows after cleaning:", len(metrics))
    print("Missing values in key fields after cleaning:")
    print(metrics[[
        "Unit_Type",
        "OLU_ID",
        "Tidal_Connectivity",
        "MEAN_RANGE_Marsh_Width",
        "MEAN_MIN_Output_Wave_Height",
        "MEAN_MAX_Output_Wave_Height",
    ]].isna().sum())
    print("Final CRS:", metrics.crs)
    print("Invalid geometries remaining:", int((~metrics.geometry.is_valid).sum()))
    metrics.to_file(
        processed_folder / "cleaned_baylands_resilience_metrics.gpkg",
        layer="analysis_units",
        driver="GPKG",
        engine="pyogrio",
    )

    # Clean BHM2020 tidal marsh polygons
    print("\nBHM2020 tidal marsh polygons")
    bhm_file = raw_folder / "BHM2020" / "BHM2020_v1_3" / "BHM2020_v1_3.gdb"
    marsh = gpd.read_file(
        bhm_file,
        layer="BaylandsHabitatMap2020_v1_3",
        engine="pyogrio",
    )

    marsh_rows_before = len(marsh)
    print("Raw shape:", marsh.shape)
    print("Raw columns:", marsh.columns.tolist())
    print("Raw CRS:", marsh.crs)
    print("Level4 classes:")
    print(marsh["Level4"].value_counts(dropna=False))

    marsh = marsh[marsh["Level4"] == "Tidal Marsh"].copy()
    print("Missing values in key fields:")
    print(marsh[["Level4", "Level5", "Status", "Project_ID"]].isna().sum())
    marsh = marsh.dropna(subset=["geometry"]).copy()
    marsh = marsh[~marsh.geometry.is_empty].copy()

    marsh_invalid = marsh.loc[~marsh.geometry.is_valid].copy()
    marsh_valid = marsh.loc[marsh.geometry.is_valid].copy()
    if len(marsh_invalid) > 0:
        marsh_invalid["_source_row"] = marsh_invalid.index
        marsh_invalid.geometry = marsh_invalid.geometry.make_valid(
            method="structure", keep_collapsed=False
        )
        marsh_invalid = marsh_invalid.explode(index_parts=False)
        marsh_invalid = marsh_invalid[
            marsh_invalid.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        ]
        marsh_invalid = marsh_invalid.dissolve(
            by="_source_row", aggfunc="first"
        ).reset_index()
        marsh_invalid = marsh_invalid.drop(columns=["_source_row"])
        marsh = pd.concat([marsh_valid, marsh_invalid])
        marsh = gpd.GeoDataFrame(marsh, geometry="geometry", crs=marsh_valid.crs)

    marsh = marsh.reset_index(drop=True)
    marsh = marsh.drop_duplicates().copy()
    if marsh.crs is not None and marsh.crs.to_epsg() is not None:
        marsh = marsh.to_crs(target_crs)

    print("Rows before cleaning:", marsh_rows_before)
    print("Rows after cleaning:", len(marsh))
    print("Missing values in key fields after cleaning:")
    print(marsh[["Level4", "Level5", "Status", "Project_ID"]].isna().sum())
    print("Final CRS:", marsh.crs)
    print("Invalid geometries remaining:", int((~marsh.geometry.is_valid).sum()))

    bhm_output = processed_folder / "cleaned_bhm2020.gpkg"
    marsh.to_file(
        bhm_output,
        layer="tidal_marsh",
        driver="GPKG",
        engine="pyogrio",
    )

    # Save the BHM2020 map boundary in the same GeoPackage
    print("\nBHM2020 map boundary")
    bhm_boundary = gpd.read_file(
        bhm_file,
        layer="BaylandsHabitatMap2020_Boundary_v1_3",
        engine="pyogrio",
    )

    boundary_rows_before = len(bhm_boundary)
    print("Raw shape:", bhm_boundary.shape)
    print("Raw columns:", bhm_boundary.columns.tolist())
    print("Raw CRS:", bhm_boundary.crs)
    bhm_boundary = bhm_boundary.dropna(subset=["geometry"]).copy()
    bhm_boundary = bhm_boundary[~bhm_boundary.geometry.is_empty].copy()

    boundary_invalid = bhm_boundary.loc[~bhm_boundary.geometry.is_valid].copy()
    boundary_valid = bhm_boundary.loc[bhm_boundary.geometry.is_valid].copy()
    if len(boundary_invalid) > 0:
        boundary_invalid["_source_row"] = boundary_invalid.index
        boundary_invalid.geometry = boundary_invalid.geometry.make_valid(
            method="structure", keep_collapsed=False
        )
        boundary_invalid = boundary_invalid.explode(index_parts=False)
        boundary_invalid = boundary_invalid[
            boundary_invalid.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        ]
        boundary_invalid = boundary_invalid.dissolve(
            by="_source_row", aggfunc="first"
        ).reset_index()
        boundary_invalid = boundary_invalid.drop(columns=["_source_row"])
        bhm_boundary = pd.concat([boundary_valid, boundary_invalid])
        bhm_boundary = gpd.GeoDataFrame(
            bhm_boundary, geometry="geometry", crs=boundary_valid.crs
        )

    bhm_boundary = bhm_boundary.reset_index(drop=True)
    bhm_boundary = bhm_boundary.drop_duplicates().copy()
    if bhm_boundary.crs is not None and bhm_boundary.crs.to_epsg() is not None:
        bhm_boundary = bhm_boundary.to_crs(target_crs)

    print("Rows before cleaning:", boundary_rows_before)
    print("Rows after cleaning:", len(bhm_boundary))
    print("Final CRS:", bhm_boundary.crs)
    print("Invalid geometries remaining:", int((~bhm_boundary.geometry.is_valid).sum()))
    bhm_boundary.to_file(
        bhm_output,
        layer="bhm_map_boundary",
        driver="GPKG",
        engine="pyogrio",
        mode="a",
    )

    # Clean SFEI Shore Inventory BHM2020 Update
    print("\nSFEI Shore Inventory BHM2020 Update")
    shore_file = (
        raw_folder
        / "SFEI_BayShoreInventory_BHM2020update_v1"
        / "SFEI_BayShoreInventory_BHM2020update_v1.gdb"
    )
    shore = gpd.read_file(
        shore_file,
        layer="SFEI_BayShoreInventory_BHM2020update_v1",
        engine="pyogrio",
    )

    shore_rows_before = len(shore)
    print("Raw shape:", shore.shape)
    print("Raw columns:", shore.columns.tolist())
    print("Raw CRS:", shore.crs)
    print("Missing values in key fields:")
    print(shore[["Segment_ID", "Class", "Fortified", "Frontage", "Bayshore_D", "BCB_Eng"]].isna().sum())
    shore = shore.dropna(subset=["geometry"]).copy()
    shore = shore[~shore.geometry.is_empty].copy()

    shore_invalid = shore.loc[~shore.geometry.is_valid].copy()
    shore_valid = shore.loc[shore.geometry.is_valid].copy()
    if len(shore_invalid) > 0:
        shore_invalid["_source_row"] = shore_invalid.index
        shore_invalid.geometry = shore_invalid.geometry.make_valid(
            method="structure", keep_collapsed=True
        )
        shore_invalid = shore_invalid.explode(index_parts=False)
        shore_invalid = shore_invalid[
            shore_invalid.geometry.geom_type.isin(["LineString", "MultiLineString"])
        ]
        shore_invalid = shore_invalid.dissolve(
            by="_source_row", aggfunc="first"
        ).reset_index()
        shore_invalid = shore_invalid.drop(columns=["_source_row"])
        shore = pd.concat([shore_valid, shore_invalid])
        shore = gpd.GeoDataFrame(shore, geometry="geometry", crs=shore_valid.crs)

    shore = shore.reset_index(drop=True)
    shore = shore.drop_duplicates().copy()
    if shore.crs is not None and shore.crs.to_epsg() is not None:
        shore = shore.to_crs(target_crs)

    print("Rows before cleaning:", shore_rows_before)
    print("Rows after cleaning:", len(shore))
    print("Missing values in key fields after cleaning:")
    print(shore[["Segment_ID", "Class", "Fortified", "Frontage", "Bayshore_D", "BCB_Eng"]].isna().sum())
    print("Final CRS:", shore.crs)
    print("Invalid geometries remaining:", int((~shore.geometry.is_valid).sum()))
    shore.to_file(
        processed_folder / "cleaned_shore_inventory_bhm2020_update.gpkg",
        layer="shore_inventory_update",
        driver="GPKG",
        engine="pyogrio",
    )

    print("\nFinished cleaning Baylands Resilience Metrics, BHM2020, and the BHM2020 Shore Inventory Update.")


if __name__ == "__main__":
    main()
