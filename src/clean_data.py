#!/usr/bin/env python3
"""Create deterministic, cleaned spatial inputs from the original raw data.

This is a preparation step only. It does not calculate transects, marsh width,
flood exposure joins, protection potential, or charts. Every run reads only
data/raw and replaces only this script's distinctly named data/processed files.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import CRS


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
TARGET_CRS = "EPSG:26910"
REGION_COUNTIES = {
    "Alameda", "Contra Costa", "Marin", "Napa", "San Francisco",
    "San Mateo", "Santa Clara", "Solano", "Sonoma",
}

# County membership is taken only from these actual source attributes. Layers
# without such an attribute need a real county boundary/crosswalk before they
# can be spatially filtered. No such county layer/crosswalk is in data/raw.
SOURCES: list[dict[str, Any]] = [
    {
        "path": "data/raw/BHM2020/BHM2020_v1_3/BHM2020_v1_3.gdb",
        "output": "cleaned_bhm2020.gpkg",
        "layers": [
            {"name": "BaylandsHabitatMap2020_v1_3", "output_layer": "tidal_marsh",
             # Verified from source Level4 value counts: exact class exists.
             "required": ["Level4"], "habitat_filter": ("Level4", "Tidal Marsh"),
             "county_field": None, "important": ["Level4", "Level5", "Status", "Project_ID"]},
            {"name": "BaylandsHabitatMap2020_Boundary_v1_3", "output_layer": "bhm_map_boundary",
             "required": [], "county_field": None, "important": []},
        ],
    },
    {
        "path": "data/raw/Baylands_Resilience_Metrics_v1_2.gdb",
        "output": "cleaned_baylands_resilience_metrics.gpkg",
        "layers": [{"name": "Analysis_Units_2020_v1_2", "output_layer": "analysis_units",
                    "required": ["Unit_Type"], "county_field": None,
                    "important": ["Unit_Type", "OLU_ID", "Tidal_Connectivity", "MEAN_RANGE_Marsh_Width",
                                  "MEAN_MIN_Output_Wave_Height", "MEAN_MAX_Output_Wave_Height"]}],
    },
    {
        "path": "data/raw/CommunityVulnerability.gdb",
        "output": "cleaned_community_vulnerability.gpkg",
        "layers": [{"name": "CommunityVulnerability_BCDC_2020", "output_layer": "community_vulnerability",
                    "required": ["GEOID", "estimate_totPop"], "county_field": None,
                    "important": ["GEOID", "NAME", "estimate_totPop", "socVulnRank", "MTC_CoC_2018"]}],
    },
    {
        "path": "data/raw/SFBayShoreInventory_SFEI_2016_0 (1)/ESRI ArcGIS/SFBayShoreInventory__SFEI_2016.gdb",
        "output": "cleaned_shore_inventory_2016.gpkg",
        "layers": [
            {"name": "San_Francisco_Bay_Shore_Inventory", "output_layer": "shore_inventory",
             "required": ["Segment_ID", "Geographic_County"], "county_field": "Geographic_County",
             "important": ["Segment_ID", "Class", "Fortified", "Frontage", "Geographic_County"]},
            {"name": "San_Francisco_Bay_Shore_Inventory__100ft_segments_with_elevation",
             "output_layer": "shore_inventory_100ft_elevation",
             "required": ["Segment_ID", "Geographic_County", "Z_Min", "Z_Max", "Z_Mean"],
             "county_field": "Geographic_County",
             "important": ["Segment_ID", "Class", "Geographic_County", "Z_Min", "Z_Max", "Z_Mean"]},
        ],
    },
    {
        "path": "data/raw/SFEI_BayShoreInventory_BHM2020update_v1/SFEI_BayShoreInventory_BHM2020update_v1.gdb",
        "output": "cleaned_shore_inventory_bhm2020_update.gpkg",
        "layers": [{"name": "SFEI_BayShoreInventory_BHM2020update_v1", "output_layer": "shore_inventory_update",
                    "required": ["Segment_ID", "Class"], "county_field": None,
                    "important": ["Segment_ID", "Class", "Fortified", "Frontage", "Bayshore_D", "BCB_Eng"]}],
    },
    {
        "path": "data/raw/VulnerableCommunities/VulnerableCommunities_Consequences_FloodExplorer_BCDC_2020.gdb",
        "output": "cleaned_flood_explorer_bcdc_2020.gpkg",
        "layers": [
            *[{"name": f"VC_SocialVulnerability_{scenario}", "output_layer": f"social_vulnerability_{scenario}",
               "required": ["CountyName", "GEOID", "TWL"], "county_field": "CountyName",
               "important": ["CountyName", "GEOID", "TWL", f"HS_{scenario}", "SUM_res_units_2010", "SUM_res_units_2040"]}
              for scenario in (12, 24, 36, 48, 52, 66, 77, 84, 96, 108)],
            *[{"name": f"VC_ContaminationVulnerability_{scenario}", "output_layer": f"contamination_vulnerability_{scenario}",
               "required": ["CountyName", "GEOID", "TWL"], "county_field": "CountyName",
               "important": ["CountyName", "GEOID", "TWL", f"HS_{scenario}", "SUM_res_units_2010", "SUM_res_units_2040"]}
              for scenario in (12, 24, 36, 48, 52, 66, 77, 84, 96, 108)],
        ],
    },
]


def canonical_value(value: Any) -> Any:
    """Convert a scalar attribute to stable JSON for exact-row fingerprints."""
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.generic):
        return canonical_value(value.item())
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def exact_record_fingerprints(frame: gpd.GeoDataFrame) -> pd.Series:
    """Hash all attributes plus exact geometry WKB (not geometric equivalence)."""
    geometry_name = frame.geometry.name
    attributes = [c for c in frame.columns if c != geometry_name]
    result: list[str] = []
    for row in frame[attributes].itertuples(index=False, name=None):
        # The geometry is added separately so all source attributes are compared.
        i = len(result)
        geom = frame.geometry.iloc[i]
        payload = json.dumps([canonical_value(v) for v in row], sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        geom_bytes = b"" if geom is None else bytes(geom.wkb)
        result.append(hashlib.sha256(payload + b"\0" + geom_bytes).hexdigest())
    # Use positional labels so duplicate/nonconsecutive source indexes cannot
    # make duplicate filtering select more rows than intended.
    return pd.Series(result, index=range(len(frame)), dtype="object")


def promote_repaired_geometry(geom: Any, source_type: str) -> tuple[Any | None, int]:
    """Keep source polygon/line dimension and count discarded lower dimensions."""
    if geom is None or geom.is_empty or not geom.is_valid:
        return None, 0
    source_type = source_type.lower()
    family = "polygon" if "polygon" in source_type else "line" if "line" in source_type else None
    if family is None:
        return geom, 0
    single = "Polygon" if family == "polygon" else "LineString"
    multi = "MultiPolygon" if family == "polygon" else "MultiLineString"
    if geom.geom_type in (single, multi):
        promoted = getattr(shapely, multi)([geom]) if geom.geom_type == single else geom
        return promoted, 0

    parts: list[Any] = []
    discarded_components = 0
    def collect(item: Any) -> None:
        nonlocal discarded_components
        if item.geom_type == single:
            parts.append(item)
        elif item.geom_type == multi:
            parts.extend(list(item.geoms))
        elif item.geom_type == "GeometryCollection":
            for child in item.geoms:
                collect(child)
        else:
            # make_valid can return line/point remnants alongside polygons.
            # They cannot be kept in the source polygon/line feature class.
            discarded_components += len(item.geoms) if hasattr(item, "geoms") else 1
    collect(geom)
    if not parts:
        return None, discarded_components
    repaired = getattr(shapely, multi)(parts)
    if not repaired.is_valid or repaired.is_empty:
        return None, discarded_components
    return repaired, discarded_components


def clean_geometry(frame: gpd.GeoDataFrame, source_type: str) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    # Repair loop uses labels, so first make source indexes unique and stable.
    frame = frame.reset_index(drop=True)
    start = len(frame)
    null_geom = frame.geometry.isna()
    empty_geom = (~null_geom) & frame.geometry.is_empty
    frame = frame.loc[~(null_geom | empty_geom)].copy()
    invalid_mask = ~frame.geometry.is_valid
    invalid_before = int(invalid_mask.sum())
    if invalid_before and "method" not in inspect.signature(shapely.make_valid).parameters:
        raise RuntimeError(
            f"Installed Shapely {shapely.__version__} does not support "
            "make_valid(method='structure'); upgrade Shapely to >=2.1."
        )
    repaired = 0
    discarded_components = 0
    unrepaired_indices: list[Any] = []
    for idx in frame.index[invalid_mask]:
        try:
            # Structure repair is substantially faster for the source's large
            # self-intersecting multipart marsh polygons. It preserves shell
            # and hole roles, which are available in the input geometry model.
            fixed, dropped = promote_repaired_geometry(
                shapely.make_valid(frame.at[idx, frame.geometry.name], method="structure"), source_type
            )
            discarded_components += dropped
        except Exception:
            fixed = None
        if fixed is None:
            unrepaired_indices.append(idx)
        else:
            frame.at[idx, frame.geometry.name] = fixed
            repaired += 1
    if unrepaired_indices:
        frame = frame.drop(index=unrepaired_indices)
    remaining_invalid = int((~frame.geometry.is_valid).sum())
    stats = {
        "null_geometry_removed": int(null_geom.sum()),
        "empty_geometry_removed": int(empty_geom.sum()),
        "invalid_geometry_found": invalid_before,
        "geometry_repaired": repaired,
        "repair_components_discarded_by_type_promotion": discarded_components,
        "unrepairable_geometry_removed": len(unrepaired_indices),
        "valid_geometry_remaining": len(frame) - remaining_invalid,
    }
    assert remaining_invalid == 0, "Invalid geometry remains after repair"
    assert len(frame) <= start
    return frame, stats


def remove_exact_duplicates(frame: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    if frame.empty:
        return frame, 0
    fingerprints = exact_record_fingerprints(frame)
    duplicate_mask = fingerprints.duplicated(keep="first").to_numpy()
    return frame.iloc[np.flatnonzero(~duplicate_mask)].copy(), int(duplicate_mask.sum())


def county_filter(frame: gpd.GeoDataFrame, field: str | None) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    if not field:
        return frame, {"status": "not_applied", "reason": "No county attribute; no county boundary/crosswalk is available."}
    if field not in frame.columns:
        raise ValueError(f"Configured county field {field!r} is missing")
    county = frame[field].astype("string").str.strip()
    # Verified source typo found in the 2016 inventory.
    spelling_corrections = {"cora costa": "Contra Costa"}
    normalized = county.map(
        lambda value: spelling_corrections.get(value.casefold(), value)
        if isinstance(value, str) else value
    )
    allowed_folded = {name.casefold() for name in REGION_COUNTIES}
    matched = normalized.str.casefold().isin(allowed_folded)
    unmatched_values = sorted(str(v) for v in normalized[~matched & normalized.notna()].unique())
    corrected_rows = int((county.str.casefold() != normalized.str.casefold()).fillna(False).sum())
    missing_county = int(normalized.isna().sum())
    # A value outside the verified allowlist may be a typo or another
    # ambiguous label, so retain it for review rather than classify it as
    # out-of-region. Only confirmed in-region values count as such.
    out = frame.copy()
    out[field] = normalized
    return out, {
        "status": "county_attribute_check",
        "field": field,
        "verified_spelling_corrections_applied": corrected_rows,
        "unmatched_values_preserved_and_reported": unmatched_values,
        "unmatched_rows_preserved": int((~matched & normalized.notna()).sum()),
        "missing_county_rows_preserved": missing_county,
        "confirmed_in_region_rows": int(matched.sum()),
    }


def missing_counts(frame: gpd.GeoDataFrame, fields: list[str]) -> dict[str, int]:
    return {field: int(frame[field].isna().sum()) for field in fields if field in frame.columns}


def duplicate_identifier_count(frame: gpd.GeoDataFrame, field: str | None) -> int | None:
    if not field or field not in frame.columns:
        return None
    non_null = frame.loc[frame[field].notna(), field]
    return int(non_null.duplicated(keep="first").sum())


def reproject(frame: gpd.GeoDataFrame, source_crs: Any) -> tuple[gpd.GeoDataFrame, str, str]:
    # Prefer the CRS attached to the loaded frame, falling back to GDAL layer
    # metadata. Never infer a CRS from coordinates or a layer name.
    source_crs = frame.crs if frame.crs is not None else source_crs
    if source_crs is None:
        return frame, "unavailable", "CRS is missing; reprojection not attempted."
    try:
        crs = CRS.from_user_input(source_crs)
    except Exception as exc:
        return frame, "unresolved", f"CRS could not be parsed ({exc}); original CRS preserved."
    epsg = crs.to_epsg()
    if epsg is None:
        # The Flood Explorer WKT says UTM Zone 10N but declares an unknown datum.
        # Do not guess the datum or transform it as if it were EPSG:26910.
        return frame, "unresolved", f"Stored CRS ({crs.name}) has no resolvable EPSG; original CRS preserved."
    if epsg == 26910:
        return frame, f"EPSG:{epsg}", "Already EPSG:26910; retained."
    frame = frame.to_crs(TARGET_CRS)
    assert frame.crs is not None and CRS.from_user_input(frame.crs).to_epsg() == 26910
    return frame, f"EPSG:{epsg}", f"Reprojected from EPSG:{epsg} to EPSG:26910."


def process_layer(source: dict[str, Any], layer_cfg: dict[str, Any], staged_output: Path,
                  first_output_layer: bool, gpkg_type: str) -> tuple[dict[str, Any], bool]:
    rel_path = source["path"]
    input_path = ROOT / rel_path
    layer = layer_cfg["name"]
    if not input_path.is_dir():
        raise FileNotFoundError(f"Required raw geodatabase not found: {rel_path}")
    info = pyogrio.read_info(input_path, layer=layer)
    input_count = int(info["features"])
    fields = set(str(x) for x in info.get("fields", []))
    absent = sorted(set(layer_cfg["required"]) - fields)
    if absent:
        raise ValueError(f"{rel_path}::{layer} missing required field(s): {absent}")

    class_removed = 0
    if "habitat_filter" in layer_cfg:
        class_field, class_value = layer_cfg["habitat_filter"]
        class_values = pyogrio.read_dataframe(input_path, layer=layer, columns=[class_field], read_geometry=False)
        selected_count = int(class_values[class_field].eq(class_value).sum())
        class_removed = input_count - selected_count
        where_value = class_value.replace("'", "''")
        frame = pyogrio.read_dataframe(input_path, layer=layer, where=f"{class_field} = '{where_value}'")
        assert len(frame) == selected_count, "Habitat SQL filter count differs from attribute scan"
    else:
        frame = pyogrio.read_dataframe(input_path, layer=layer)
    assert len(frame) == input_count - class_removed

    source_geometry_type = str(info.get("geometry_type") or "")
    frame, geometry_stats = clean_geometry(frame, source_geometry_type)
    before_dedupe = len(frame)
    frame, duplicate_rows_removed = remove_exact_duplicates(frame)

    county_identifier = "Segment_ID" if "Segment_ID" in frame.columns else "GEOID" if "GEOID" in frame.columns else None
    duplicate_ids_before = duplicate_identifier_count(frame, county_identifier)
    frame, county_stats = county_filter(frame, layer_cfg.get("county_field"))
    if layer == "CommunityVulnerability_BCDC_2020":
        assert duplicate_identifier_count(frame, "GEOID") == 0, "GEOID must be unique where non-null"

    population_stats: dict[str, int] = {}
    if "estimate_totPop" in frame.columns:
        original_pop = frame["estimate_totPop"]
        pop = pd.to_numeric(original_pop, errors="coerce")
        missing_before = int(original_pop.isna().sum())
        unparseable = original_pop.notna() & pop.isna()
        negative = pop < 0
        nonfinite = pop.notna() & ~np.isfinite(pop.astype(float))
        invalid = unparseable | negative | nonfinite
        invalid_count = int(invalid.sum())
        # Preserve the spatial/community row, but mark invalid estimates missing.
        # Existing nulls remain null; no missing value is replaced by zero.
        pop = pop.astype("float64")
        pop.loc[invalid] = np.nan
        frame["estimate_totPop"] = pop
        population_stats = {
            "missing_population_before": missing_before,
            "unparseable_negative_or_nonfinite_population_set_missing": invalid_count,
            "missing_population_after": int(frame["estimate_totPop"].isna().sum()),
            "zero_population_retained": int((pd.to_numeric(frame["estimate_totPop"], errors="coerce") == 0).sum()),
        }
        final_pop = pd.to_numeric(frame["estimate_totPop"], errors="coerce")
        assert not (final_pop.dropna() < 0).any()

    missing = missing_counts(frame, layer_cfg.get("important", []))
    frame, source_crs, reprojection = reproject(frame, info.get("crs"))
    expected_epsg = 26910 if source_crs != "unresolved" and source_crs != "unavailable" else None
    if expected_epsg:
        assert CRS.from_user_input(frame.crs).to_epsg() == expected_epsg
    assert frame.geometry.notna().all()
    assert (~frame.geometry.is_empty).all()
    assert frame.geometry.is_valid.all()

    output_layer = layer_cfg["output_layer"]
    frame.to_file(staged_output, layer=output_layer, driver="GPKG", engine="pyogrio",
                  mode="w" if first_output_layer else "a")

    # Validate what was written from the staged output, without reading it back
    # into memory (feature count and CRS come from GDAL metadata).
    out_info = pyogrio.read_info(staged_output, layer=output_layer)
    output_epsg = None
    if out_info.get("crs"):
        try:
            output_epsg = CRS.from_user_input(out_info["crs"]).to_epsg()
        except Exception:
            pass
    assert int(out_info["features"]) == len(frame)
    if expected_epsg:
        assert output_epsg == 26910, f"Output CRS is {output_epsg}, expected EPSG:26910"
    assert len(frame) <= before_dedupe

    summary = {
        "source": rel_path,
        "input_layer": layer,
        "input_features": input_count,
        "irrelevant_habitat_class_removed": class_removed,
        **geometry_stats,
        "exact_duplicate_records_removed": duplicate_rows_removed,
        "duplicate_identifier_rows_remaining": duplicate_identifier_count(frame, county_identifier),
        "duplicate_identifier_field": county_identifier,
        "duplicate_identifier_rows_before_county_filter": duplicate_ids_before,
        "county_filter": county_stats,
        "population": population_stats or None,
        "important_field_missing_counts_after_cleaning": missing,
        "output_features": len(frame),
        "input_crs": source_crs,
        "crs_action": reprojection,
        "reprojected_features": len(frame) if reprojection.startswith("Reprojected") else 0,
        "final_crs": (f"EPSG:{output_epsg}" if output_epsg else
                       "missing CRS preserved" if source_crs == "unavailable" else
                       "unresolved source CRS preserved"),
        "output": staged_output.relative_to(ROOT).as_posix().replace(".staging", ""),
    }
    return summary, False


def main() -> int:
    if not RAW.is_dir():
        raise FileNotFoundError(f"Raw data directory not found: {RAW}")
    # This polygon extent is the BHM map boundary, not a nine-county boundary.
    boundary_candidates = [p for p in RAW.rglob("*") if p.is_file() and
                           p.suffix.lower() in {".shp", ".gpkg", ".geojson"} and "count" in p.name.lower()]
    if not boundary_candidates:
        print("DEPENDENCY: no county boundary/crosswalk found in data/raw; county filtering is limited to explicit source county fields.")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    staged_files: list[tuple[Path, Path]] = []

    with tempfile.TemporaryDirectory(prefix="clean_data_", dir=PROCESSED) as temp_dir:
        stage_root = Path(temp_dir)
        for source in SOURCES:
            output_relative = Path("data/processed") / source["output"]
            staged_output = stage_root / (source["output"] + ".staging.gpkg")
            # GPKG permits multiple layer tables; each gets a distinct safe name.
            for index, layer_cfg in enumerate(source["layers"]):
                if staged_output.exists() and index == 0:
                    staged_output.unlink()
                summary, _ = process_layer(source, layer_cfg, staged_output, index == 0, "GPKG")
                summary["output"] = output_relative.as_posix()
                summaries.append(summary)
            # Verify that GDAL sees every expected layer and that no write failed.
            written_layers = {str(row[0]) for row in pyogrio.list_layers(staged_output)}
            expected_layers = {cfg["output_layer"] for cfg in source["layers"]}
            assert written_layers == expected_layers, f"Output layers mismatch: {written_layers} != {expected_layers}"
            staged_files.append((staged_output, ROOT / output_relative))

        # Replace only the distinct cleaned filenames owned by this script.
        for staged, target in staged_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)

    print("\nCleaning summary (source data remains unchanged):")
    for row in summaries:
        county = row["county_filter"]
        county_text = (f"county confirmed in-region={county.get('confirmed_in_region_rows', 0)}, "
                       f"unmatched rows preserved={county.get('unmatched_rows_preserved', 0)} "
                       f"({county.get('unmatched_values_preserved_and_reported', [])}), "
                       f"missing county preserved={county.get('missing_county_rows_preserved', 0)}, "
                       f"verified spelling fixes={county.get('verified_spelling_corrections_applied', 0)}" if county["status"] == "county_attribute_check"
                       else "county filter=not applied; boundary/crosswalk unavailable")
        print(
            f"- {row['input_layer']}: {row['source']} | input={row['input_features']} "
            f"class-filtered={row['irrelevant_habitat_class_removed']} "
            f"null/empty geom removed={row['null_geometry_removed']}/{row['empty_geometry_removed']} "
            f"invalid={row['invalid_geometry_found']} repaired={row['geometry_repaired']} "
            f"repair components discarded={row['repair_components_discarded_by_type_promotion']} "
            f"unrepairable removed={row['unrepairable_geometry_removed']} "
            f"exact duplicates removed={row['exact_duplicate_records_removed']} "
            f"duplicate-ID rows={row['duplicate_identifier_rows_remaining']} "
            f"{county_text} | final={row['output_features']} "
            f"missing={row['important_field_missing_counts_after_cleaning']} "
            f"reprojected features={row['reprojected_features']} ({row['crs_action']}) "
            f"CRS={row['final_crs']} | {row['output']}"
        )
        if row["population"]:
            print(f"  population: {row['population']}")
    print("\nCounty boundary filtering was not attempted for layers without an explicit county field.")
    unresolved = [f"{row['input_layer']}: {row['crs_action']}" for row in summaries
                  if row["input_crs"] in {"unresolved", "unavailable"}]
    if unresolved:
        print("MANUAL CRS VERIFICATION REQUIRED (no reprojection was guessed):")
        for item in unresolved:
            print(f"- {item}")
    print("BHM ZIP copy and KMZ display exports were not processed; the extracted source geodatabases were used.")
    print(f"Prepared {len(staged_files)} GeoPackage(s) with {len(summaries)} layers under data/processed/.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
