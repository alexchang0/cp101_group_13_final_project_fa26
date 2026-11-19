# Interactive map of how much each marsh shrinks
# the 100-year wave, on top of BCDC's social vulnerability
# rank for each block group.

from pathlib import Path

import geopandas as gpd
from lonboard import Map, PolygonLayer
from lonboard.basemap import MaplibreBasemap, CartoStyle
from lonboard.colormap import apply_continuous_cmap, apply_categorical_cmap
from palettable.colorbrewer.sequential import Greens_9, OrRd_4

root = Path(__file__).resolve().parents[1]

# marsh units with wave data (same steps as wave_attenuation.py)
marsh = gpd.read_parquet(root / "data/processed/cleaned_baylands_resilience_metrics.parquet")
marsh = marsh.rename(columns={"MEAN_MAX_Output_Wave_Height": "wave_offshore_ft", "MEAN_MIN_Output_Wave_Height": "wave_back_of_marsh_ft"})
marsh = marsh.dropna(subset=["wave_offshore_ft", "wave_back_of_marsh_ft"])
marsh = marsh[(marsh["wave_offshore_ft"] < 20) & (marsh["wave_back_of_marsh_ft"] < 20)]
marsh["attenuation_ft"] = marsh["wave_offshore_ft"] - marsh["wave_back_of_marsh_ft"]
marsh["attenuation_pct"] = marsh["attenuation_ft"] / marsh["wave_offshore_ft"] * 100

marsh = marsh[["OLU_Name", "Subembayment_Name", "wave_offshore_ft", "wave_back_of_marsh_ft", "attenuation_ft", "attenuation_pct", "geometry"]].round(2)
# simplify to 10 m to keep the html small
marsh["geometry"] = marsh.simplify(10)
marsh = marsh.to_crs(4326)  # lonboard needs lon/lat coordinates
print("marsh units:", len(marsh))

# block groups with social vulnerability rank
gdb = root / "data/raw/e221c89f-01bd-4e37-a742-31a7735df244.gdb"
blocks = gpd.read_file(gdb, layer="CommunityVulnerability_BCDC_2020", columns=["GEOID", "socVulnRank"])
blocks["geometry"] = blocks.simplify(25)
blocks = blocks.to_crs(4326)
print("block groups:", len(blocks))

# colors: darker green = marsh cuts the wave more
marsh_colors = apply_continuous_cmap(marsh["attenuation_pct"] / 100, Greens_9)

# click a marsh to see data. columns renamed and data rounded.
marsh = gpd.GeoDataFrame({"Location": marsh["OLU_Name"], "Bay": marsh["Subembayment_Name"],
                          "Wave in": marsh["wave_offshore_ft"].round(2).astype(str) + " ft", "Wave out": marsh["wave_back_of_marsh_ft"].round(2).astype(str) + " ft",
                          "Reduced": marsh["attenuation_pct"].round().astype(int).astype(str) + "%"}, geometry=marsh["geometry"]).reset_index(drop=True)

# 4 shades light to dark
rank_colors = {"Low social vulnerability": OrRd_4.colors[0], "Moderate social vulnerability": OrRd_4.colors[1], "High social vulnerability": OrRd_4.colors[2],
               "Highest social vulnerability": OrRd_4.colors[3], "Not Calculated": [200, 200, 200]}
block_colors = apply_categorical_cmap(blocks["socVulnRank"].astype("category"), rank_colors, alpha=90)

block_layer = PolygonLayer.from_geopandas(blocks, get_fill_color=block_colors, get_line_color=[255, 255, 255], line_width_min_pixels=0.3)
marsh_layer = PolygonLayer.from_geopandas(marsh, get_fill_color=marsh_colors, get_line_color=[0, 68, 27], line_width_min_pixels=1)

m = Map([block_layer, marsh_layer], basemap=MaplibreBasemap(style=CartoStyle.Positron), view_state={"longitude": -122.25, "latitude": 37.8, "zoom": 9})

maps = root / "outputs/maps"
maps.mkdir(parents=True, exist_ok=True)
m.to_html(maps / "marsh_wave_attenuation_map.html")
print("saved map")
