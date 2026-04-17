import pandas as pd
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent          # src/
DATA_DIR     = BASE_DIR.parent.parent            # project root (one level up from src/)
print(BASE_DIR)
print(DATA_DIR)
FAIR_FILE    = DATA_DIR / "data" /"ass"/ "KGHBeatassessmentResult"/"FAIRASSInput"/ "2025-04-27.csv"
SUBCLOUD_DIR = DATA_DIR / "data" /"LODsubclouds"
OUTPUT_DIR   = DATA_DIR / "data" / "ass" / "KGHBeatassessmentResult"/"FAIRASSout"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load FAIR data ────────────────────────────────────────────────────────────
print("Loading FAIR assessment …")
fair = pd.read_csv(FAIR_FILE, low_memory=False)

meaningful_cols = [c for c in fair.columns if not str(c).startswith("Unnamed:")]
fair = fair[meaningful_cols]
fair["KG id"] = fair["KG id"].astype(str).str.strip()
print(f"  FAIR rows: {len(fair)}, columns kept: {len(meaningful_cols)}")

# ── Process each sub-cloud file ───────────────────────────────────────────────
subcloud_files = sorted(SUBCLOUD_DIR.glob("*.csv"))
if not subcloud_files:
    raise FileNotFoundError(f"No CSV files found in {SUBCLOUD_DIR}")

for sc_path in subcloud_files:
    topic = sc_path.stem
    sc = pd.read_csv(sc_path)
    sc["id"] = sc["id"].astype(str).str.strip()

    merged = sc.merge(fair, left_on="id", right_on="KG id", how="left")

    if "KG id" in merged.columns:
        merged = merged.drop(columns=["KG id"])

    out_path = OUTPUT_DIR / f"{topic}.csv"
    merged.to_csv(out_path, index=False)

    matched = merged["KG name"].notna().sum()
    print(f"  ✓ {topic}.csv  →  {len(sc)} ids, {matched} matched with FAIR data")

print(f"\nDone — merged CSVs written to '{OUTPUT_DIR}'")