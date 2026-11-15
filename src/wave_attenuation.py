# Wave attenuation by marsh unit, using SFEI's Baylands Resilience Metrics.
# SFEI's web map defines attenuation as the 100-year wave height offshore
# minus the 100-year wave height at the back of the marsh (feet).

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

root = Path(__file__).resolve().parents[1]
metrics = pd.read_parquet(root / "data/processed/cleaned_baylands_resilience_metrics.parquet")

columns = {
    "MEAN_MAX_Output_Wave_Height": "wave_offshore_ft",
    "MEAN_MEAN_Mudflat_Edge_Wave_Height": "wave_marsh_edge_ft",
    "MEAN_MIN_Output_Wave_Height": "wave_back_of_marsh_ft",
    "MEAN_RANGE_Marsh_Width": "marsh_width_ft",
    "MEAN_MEAN_Marsh_Width_Needed": "extra_width_ft",
    "MEDIAN_Mudflat_Contribution": "mudflat_pct",
}
waves = metrics[["OLU_ID", "OLU_Name", "Subembayment_Name", "Majority_Class"] + list(columns)]
waves = waves.rename(columns=columns)

# only bay-facing marshes were modeled, so most units have no wave values
waves = waves.dropna(subset=["wave_offshore_ft", "wave_back_of_marsh_ft"])

# a few units have broken values (around 1e27), so drop anything over 20 ft
waves = waves[(waves["wave_offshore_ft"] < 20) & (waves["wave_back_of_marsh_ft"] < 20)]

waves["attenuation_ft"] = waves["wave_offshore_ft"] - waves["wave_back_of_marsh_ft"]
waves["attenuation_pct"] = waves["attenuation_ft"] / waves["wave_offshore_ft"] * 100

print("marsh units with wave data:", len(waves))
print(waves[["wave_offshore_ft", "wave_back_of_marsh_ft", "attenuation_ft", "attenuation_pct"]].describe().round(2))

by_bay = waves.groupby("Subembayment_Name").agg(
    units=("attenuation_ft", "count"),
    wave_offshore_ft=("wave_offshore_ft", "median"),
    wave_back_of_marsh_ft=("wave_back_of_marsh_ft", "median"),
    attenuation_ft=("attenuation_ft", "median"),
    attenuation_pct=("attenuation_pct", "median"),
).round(2)
print(by_bay)

by_olu = waves.groupby(["OLU_ID", "OLU_Name"]).agg(
    units=("attenuation_ft", "count"),
    wave_offshore_ft=("wave_offshore_ft", "median"),
    wave_back_of_marsh_ft=("wave_back_of_marsh_ft", "median"),
    attenuation_ft=("attenuation_ft", "median"),
    attenuation_pct=("attenuation_pct", "median"),
).round(2).reset_index()

tables = root / "outputs/tables"
tables.mkdir(parents=True, exist_ok=True)
waves.to_csv(tables / "wave_attenuation_by_unit.csv", index=False)
by_bay.to_csv(tables / "wave_attenuation_by_subembayment.csv")
by_olu.to_csv(tables / "wave_attenuation_by_olu.csv", index=False)

# chart: median wave height offshore vs back of marsh for each subembayment
by_bay = by_bay.sort_values("wave_offshore_ft")
fig, ax = plt.subplots(figsize=(9, 5))
y = range(len(by_bay))
ax.barh([i + 0.2 for i in y], by_bay["wave_offshore_ft"], height=0.4, color="#4a7fb0", label="Offshore")
ax.barh([i - 0.2 for i in y], by_bay["wave_back_of_marsh_ft"], height=0.4, color="#79ad78", label="Back of marsh")
ax.set_yticks(list(y))
ax.set_yticklabels(by_bay.index)
ax.set_xlabel("Median 100-year wave height (ft)")
ax.set_title("How much marshes shrink 100-year waves, by part of the Bay")
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)

figures = root / "outputs/figures"
figures.mkdir(parents=True, exist_ok=True)
fig.savefig(figures / "wave_attenuation_by_subembayment.png", dpi=200, bbox_inches="tight")
print("saved tables and chart")
