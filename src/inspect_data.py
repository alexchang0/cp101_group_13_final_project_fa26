#!/usr/bin/env python3
"""Inspect raw GIS data without modifying source files.

Uses installed GDAL bindings through Pyogrio/Fiona/GeoPandas and Rasterio where
available. All reads are bounded to a small sample except for driver metadata
operations such as feature counts and bounds. Errors are retained in outputs.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
JSON_OUT = ROOT / "outputs" / "tables" / "data_inventory.json"
SAMPLE_SIZE = 8

MODULES = ("geopandas", "pyogrio", "fiona", "osgeo", "rasterio", "shapely", "pandas")
INSTALL = "python -m pip install geopandas pyogrio rasterio (or python -m pip install fiona rasterio; install GDAL/FileGDB support compatible with your platform)"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    return str(value)


def import_status() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in MODULES}


def identify_fields(fields: list[str], samples: list[dict[str, Any]]) -> dict[str, list[str]]:
    categories = {
        "identifier": ("id", "fid", "objectid", "globalid", "geoid", "segment", "tract", "block", "code"),
        "classification": ("class", "type", "category", "status", "habitat", "level", "landuse"),
        "population": ("population", "pop", "resident", "household", "unit", "housing", "building"),
        "flood_scenario": ("flood", "scenario", "depth", "inundat", "return", "waterlevel", "slr", "surge"),
        "vulnerability_equity": ("vulner", "equity", "priority", "social", "disadv", "income", "race", "svi"),
        "marsh_habitat": ("marsh", "wetland", "habitat", "tidal", "vegetat"),
        "shoreline": ("shore", "shoreline", "segment", "fortif", "frontage", "revet", "seawall", "bayshore"),
    }
    found: dict[str, list[str]] = {}
    for label, needles in categories.items():
        found[label] = [f for f in fields if any(n in f.lower() for n in needles)]
    # Add sample evidence for numeric fields that could be population or scenario values.
    return found


def sample_value_summary(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    by_field: dict[str, list[Any]] = {}
    for row in rows:
        for key, value in row.items():
            if key.lower() in {"geometry", "shape"}:
                continue
            values = by_field.setdefault(key, [])
            value = json_safe(value)
            if value is not None and value not in values and len(values) < 5:
                values.append(value)
    return by_field


def inspect_layer(path: Path, layer: str | None, method: str) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path.relative_to(ROOT).as_posix(), "layer": layer, "method": method}
    try:
        rows: list[dict[str, Any]] = []
        if method == "pyogrio":
            import pyogrio
            info = pyogrio.read_info(path, layer=layer)
            epsg = None
            if info.get("crs"):
                try:
                    from pyproj import CRS
                    epsg = CRS.from_user_input(info["crs"]).to_epsg()
                except Exception:
                    pass
            result.update({
                "feature_count": json_safe(info.get("features")),
                "geometry_type": json_safe(info.get("geometry_type")),
                "crs": json_safe(info.get("crs")),
                "epsg": epsg,
                "total_bounds": json_safe(info.get("total_bounds")),
                "fields": [{"name": str(n), "type": str(t)} for n, t in zip(info.get("fields", []), info.get("dtypes", []))],
            })
            frame = pyogrio.read_dataframe(path, layer=layer, max_features=SAMPLE_SIZE, read_geometry=True)
            attr_frame = frame.drop(columns=[frame.geometry.name], errors="ignore") if hasattr(frame, "geometry") else frame
            rows = attr_frame.head(SAMPLE_SIZE).to_dict(orient="records")
            result["sample_rows"] = json_safe(rows)
            result["sample_geometry_types"] = sorted(str(x) for x in frame.geometry.geom_type.dropna().unique())
            try:
                result["sample_validity"] = {"checked": int(frame.geometry.notna().sum()), "invalid": int((~frame.geometry.is_valid).sum())}
            except Exception as e:
                result["sample_validity_error"] = str(e)
        elif method == "fiona":
            import fiona
            with fiona.open(path, layer=layer) as src:
                result.update({"feature_count": len(src), "geometry_type": src.schema.get("geometry"), "crs": src.crs_wkt or dict(src.crs) or None,
                               "total_bounds": list(src.bounds) if src.bounds else None,
                               "fields": [{"name": k, "type": v} for k, v in src.schema.get("properties", {}).items()]})
                for feature in src:
                    if len(rows) >= SAMPLE_SIZE: break
                    rows.append(dict(feature["properties"]))
                result["sample_rows"] = json_safe(rows)
        else:
            import geopandas as gpd
            frame = gpd.read_file(path, layer=layer, rows=SAMPLE_SIZE)
            result.update({"feature_count": None, "geometry_type": sorted(str(x) for x in frame.geometry.geom_type.dropna().unique()),
                           "crs": str(frame.crs) if frame.crs else None,
                           "total_bounds": json_safe(frame.total_bounds.tolist()) if len(frame) else None,
                           "fields": [{"name": str(k), "type": str(v)} for k, v in frame.dtypes.items()]})
            rows = frame.drop(columns=[frame.geometry.name], errors="ignore").to_dict(orient="records")
            result["sample_rows"] = json_safe(rows)
            try: result["sample_validity"] = {"checked": int(frame.geometry.notna().sum()), "invalid": int((~frame.geometry.is_valid).sum())}
            except Exception as e: result["sample_validity_error"] = str(e)
            fields = list(frame.columns)
        result["representative_values"] = sample_value_summary(rows)
        result["likely_field_roles"] = identify_fields([f["name"] for f in result.get("fields", [])], rows)
        # Nulls and duplicate IDs are deliberately sample-scoped to avoid unbounded reads.
        attrs = [r for r in rows]
        result["sample_null_counts"] = {k: sum(r.get(k) is None for r in attrs) for k in (attrs[0].keys() if attrs else [])}
        id_candidates = result["likely_field_roles"].get("identifier", [])
        result["sample_duplicate_identifiers"] = {}
        for key in id_candidates:
            vals = [json_safe(r.get(key)) for r in attrs if r.get(key) is not None]
            dup = sorted(str(v) for v, n in Counter(map(str, vals)).items() if n > 1)
            result["sample_duplicate_identifiers"][key] = dup
        result["status"] = "ok"
    except Exception as exc:
        result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return result


def inspect_raster(path: Path) -> dict[str, Any]:
    result = {"path": path.relative_to(ROOT).as_posix(), "kind": "raster", "method": "rasterio"}
    try:
        import rasterio
        with rasterio.open(path) as ds:
            result.update({"status": "ok", "width": ds.width, "height": ds.height, "band_count": ds.count,
                           "crs": ds.crs.to_string() if ds.crs else None,
                           "epsg": ds.crs.to_epsg() if ds.crs else None,
                           "resolution": list(ds.res), "bounds": list(ds.bounds), "nodata": list(ds.nodatavals),
                           "dtypes": list(ds.dtypes)})
    except Exception as exc:
        result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return result


def inspect_tabular(path: Path) -> dict[str, Any]:
    result = {"path": path.relative_to(ROOT).as_posix(), "kind": "tabular", "method": "csv module"}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                rows.append(row)
                if len(rows) >= SAMPLE_SIZE: break
            result.update({"status": "ok", "fields": reader.fieldnames or [], "sample_rows": rows,
                           "representative_values": sample_value_summary(rows), "sampled_rows": len(rows),
                           "likely_field_roles": identify_fields(reader.fieldnames or [], rows)})
    except Exception as exc:
        result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return result


def main() -> int:
    libs = import_status()
    data: dict[str, Any] = {"generated_at": __import__("datetime").datetime.now().astimezone().isoformat(),
                            "root": ".", "raw_root": "data/raw", "libraries": libs, "install_guidance": INSTALL,
                            "sample_size": SAMPLE_SIZE, "datasets": [], "other_files": []}
    if not RAW.exists():
        data["fatal_error"] = f"Raw data directory does not exist: {RAW}"
    else:
        gdbs = sorted(p for p in RAW.rglob("*.gdb") if p.is_dir())
        covered = set(gdbs)
        vector_available = "pyogrio" if libs["pyogrio"] else "fiona" if libs["fiona"] else "geopandas" if libs["geopandas"] else None
        for gdb in gdbs:
            if vector_available:
                try:
                    if vector_available == "pyogrio":
                        import pyogrio
                        layers = pyogrio.list_layers(gdb)
                    elif vector_available == "fiona":
                        import fiona
                        layers = fiona.listlayers(gdb)
                    else:
                        import fiona
                        layers = fiona.listlayers(gdb)
                    if len(layers) == 0:
                        data["datasets"].append({"path": gdb.relative_to(ROOT).as_posix(), "kind": "FileGDB", "status": "ok", "layers": [], "method": vector_available})
                    for layer_info in layers:
                        # Pyogrio returns an ndarray shaped (n_layers, 2), while
                        # Fiona returns plain strings. Select the first cell in
                        # each Pyogrio row (layer name), not its whole row.
                        layer = str(layer_info[0] if not isinstance(layer_info, str) and hasattr(layer_info, "__len__") else layer_info)
                        data["datasets"].append(inspect_layer(gdb, layer, vector_available))
                except Exception as exc:
                    data["datasets"].append({"path": gdb.relative_to(ROOT).as_posix(), "kind": "FileGDB", "method": vector_available, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            else:
                data["datasets"].append({"path": gdb.relative_to(ROOT).as_posix(), "kind": "FileGDB", "method": "Pyogrio/Fiona/GDAL discovery unavailable", "status": "error", "error": "No installed vector reader (pyogrio, fiona, geopandas)."})
        raster_ext = {".tif", ".tiff", ".img", ".jp2", ".vrt", ".asc", ".nc"}
        vector_ext = {".shp", ".gpkg", ".geojson", ".json", ".gml", ".kml", ".kmz", ".tab", ".mif", ".sqlite"}
        tabular_ext = {".csv", ".tsv"}
        for p in sorted(x for x in RAW.rglob("*") if x.is_file()):
            if any(parent in p.parents for parent in covered):
                continue
            ext = p.suffix.lower()
            if ext in raster_ext:
                data["datasets"].append(inspect_raster(p))
            elif ext in vector_ext:
                if vector_available:
                    method = vector_available
                    target = p
                    if ext == ".kmz":
                        # KMZ is a zip container; inspect its KML entries only, without extracting to source.
                        try:
                            with zipfile.ZipFile(p) as zf:
                                kmls = [n for n in zf.namelist() if n.lower().endswith(".kml")]
                            if not kmls:
                                raise ValueError("KMZ contains no KML member")
                            data["datasets"].append({"path": p.relative_to(ROOT).as_posix(), "kind": "KMZ", "method": "archive listing", "members": kmls, "status": "present; vector features not decoded"})
                            continue
                        except Exception as exc:
                            data["datasets"].append({"path": p.relative_to(ROOT).as_posix(), "kind": "KMZ", "method": "zipfile", "status": "error", "error": f"{type(exc).__name__}: {exc}"})
                            continue
                    data["datasets"].append(inspect_layer(target, None, method))
                else:
                    data["datasets"].append({"path": p.relative_to(ROOT).as_posix(), "kind": "vector file", "method": "Pyogrio/Fiona/GDAL unavailable", "status": "error", "error": "No installed vector reader (pyogrio, fiona, geopandas)."})
            elif ext in tabular_ext:
                data["datasets"].append(inspect_tabular(p))
            else:
                size = p.stat().st_size
                cls = "ZIP archive containing data" if ext == ".zip" else "ArcGIS layer/map/document or other supporting file" if ext in {".lyr", ".lyrx", ".mxd", ".pdf", ".ds_store"} else "other file; not an identified GIS data format"
                item = {"path": p.relative_to(ROOT).as_posix(), "size_bytes": size, "classification": cls}
                if ext == ".zip":
                    try:
                        with zipfile.ZipFile(p) as zf:
                            item["archive_entries"] = len(zf.infolist())
                            item["contained_gdbs"] = sorted({n.split(".gdb/", 1)[0] + ".gdb" for n in zf.namelist() if ".gdb/" in n})
                    except Exception as exc: item["error"] = f"{type(exc).__name__}: {exc}"
                data["other_files"].append(item)
                for embedded in item.get("contained_gdbs", []):
                    data["datasets"].append({"path": f"{p.relative_to(ROOT).as_posix()}!/{embedded}", "kind": "FileGDB inside ZIP", "method": "archive listing; no extraction attempted", "status": "error", "error": "The archive contains this FileGDB, but the inspector does not extract or open FileGDB directories inside ZIP archives."})
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(json_safe(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    print("Libraries:", json.dumps(libs))
    print(f"Dataset entries: {len(data['datasets'])}; errors: {sum(d.get('status') == 'error' for d in data['datasets'])}")
    if not any(libs.get(x) for x in ("pyogrio", "fiona", "geopandas")):
        print("Vector inspection could not run; see report and install guidance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
