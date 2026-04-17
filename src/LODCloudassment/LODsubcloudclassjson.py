
import json
import os
from pathlib import Path
BASE_DIR     = Path(__file__).parent          # src/
DATA_DIR     = BASE_DIR.parent.parent
INPUT_FILE = DATA_DIR  / "data" /"ass"/ "KGHBeatassessmentResult"/"FAIRASSInput"/ "kgs_by_topic.json"
OUTPUT_DIR = DATA_DIR  /  "data" /"ass"/ "KGHBeatassessmentResult"/"LODsubclouds"



def extract_id(url: str) -> str:
    """Return the last path segment of a URL as the dataset ID."""
    return url.rstrip("/").split("/")[-1]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_FILE, encoding="utf-8") as f:
        data: dict[str, list[str]] = json.load(f)

    summary = {}

    for topic, urls in data.items():
        ids = [extract_id(url) for url in urls]

        # Build output payload
        payload = {
            "topic": topic,
            "count": len(ids),
            "ids": ids,
        }

        out_path = OUTPUT_DIR / f"{topic}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        summary[topic] = len(ids)
        print(f"  ✓ {topic}.json  ({len(ids)} ids)")

    # Write a summary index
    index_path = OUTPUT_DIR / "_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  ✓ _index.json  (summary of all topics)")
    print(f"\nDone — {len(data)} topic files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()