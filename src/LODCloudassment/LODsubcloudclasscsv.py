import json
import csv
from pathlib import Path

BASE_DIR     = Path(__file__).parent          # src/
DATA_DIR     = BASE_DIR.parent.parent
INPUT_FILE = DATA_DIR  / "data" /"ass"/ "KGHBeatassessmentResult"/"FAIRASSInput"/ "kgs_by_topic.json"
OUTPUT_DIR = DATA_DIR  /  "data" /"LODsubclouds"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
print(BASE_DIR)
print("Data",DATA_DIR)
with open(INPUT_FILE, encoding="utf-8") as f:
    data = json.load(f)

for topic, urls in data.items():
    out_path = OUTPUT_DIR / f"{topic}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id"])
        for url in urls:
            id_ = url.rstrip("/").split("/")[-1]
            writer.writerow([id_])
    print(f"✓ {topic}.csv  ({len(urls)} ids)")

print(f"\nDone — {len(data)} CSV files written to '{OUTPUT_DIR}'")