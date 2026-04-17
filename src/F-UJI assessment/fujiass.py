import requests
import pandas as pd
import time
import json
from pathlib import Path

# -----------------------------
# CONFIG

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent          # src/
DATA_DIR     = BASE_DIR.parent.parent            # project root (one level up from src/)
print(BASE_DIR)
print(DATA_DIR)
FAIR_FILE    = DATA_DIR / "data" /"ass"/ "KGHBeatassessmentResult"/"FAIRASSInput"/ "2025-04-27.csv"
SUBCLOUD_DIR = DATA_DIR / "data" /"LODsubclouds"
OUTPUT_DIR     =DATA_DIR/ "data" / "ass" / "F-UJIassessmentResult"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


DEBUG_RESPONSE = OUTPUT_DIR / "debug_first_response.json"

# Local F-UJI server
FUJI_API      = "http://localhost:1071/fuji/api/v1/evaluate"
FUJI_USER     = "marvel"
FUJI_PASSWORD = "wonderwoman"

REQUEST_DELAY = 3
TIMEOUT       = 120
LOD_BASE_URL  = "https://lod-cloud.net/dataset/"


# -----------------------------
# EXTRACT SUMMARY SCORES
# -----------------------------
def extract_summary_scores(summary: dict, url: str) -> dict:
    score_earned  = summary.get("score_earned", {})
    score_total   = summary.get("score_total", {})
    score_percent = summary.get("score_percent", {})
    status_total  = summary.get("status_total", {})
    status_passed = summary.get("status_passed", {})
    maturity      = summary.get("maturity", {})

    result = {"url": url}

    for key in score_earned:
        safe_key = key.replace(".", "_")
        result[f"score_earned_{safe_key}"]  = score_earned.get(key)
        result[f"score_total_{safe_key}"]   = score_total.get(key)
        result[f"score_percent_{safe_key}"] = score_percent.get(key)
        result[f"status_total_{safe_key}"]  = status_total.get(key)
        result[f"status_passed_{safe_key}"] = status_passed.get(key)
        result[f"maturity_{safe_key}"]      = maturity.get(key)

    return result


# -----------------------------
# FAIR EVALUATION FUNCTION
# -----------------------------
def evaluate_with_fuji(url: str, save_debug: bool = False) -> dict | None:
    payload = {
        "object_identifier": url,
        "test_debug": False,
        "use_datacite": True,
        "use_crossref": True
    }

    try:
        response = requests.post(
            FUJI_API,
            json=payload,
            auth=(FUJI_USER, FUJI_PASSWORD),
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            print(f"   ❌ HTTP {response.status_code}")
            return None

        data = response.json()

        if save_debug:
            with open(DEBUG_RESPONSE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        if "summary" not in data:
            return None

        result = extract_summary_scores(data["summary"], url)

        for metric in data.get("results", []):
            raw_id    = metric.get("metric_identifier", "")
            metric_id = raw_id.replace("-", "_").replace(".", "_")
            score_block = metric.get("score", {})

            result[f"{metric_id}_earned"]   = score_block.get("earned", 0)
            result[f"{metric_id}_total"]    = score_block.get("total", 0)
            result[f"{metric_id}_maturity"] = metric.get("maturity", 0)
            result[f"{metric_id}_status"]   = metric.get("test_status", "")

            for test_id, test_data in metric.get("metric_tests", {}).items():
                clean_test_id = test_id.replace("-", "_").replace(".", "_")
                test_score = test_data.get("metric_test_score", {})
                result[f"{clean_test_id}_earned"]   = test_score.get("earned", 0)
                result[f"{clean_test_id}_total"]    = test_score.get("total", 0)
                result[f"{clean_test_id}_status"]   = test_data.get("metric_test_status", "")
                result[f"{clean_test_id}_maturity"] = test_data.get("metric_test_maturity", 0)

        return result

    except Exception as e:
        print(f"   ⚠️ Error: {e}")
        return None


# -----------------------------
# SERVER CHECK
# -----------------------------
def check_server():
    try:
        r = requests.get("http://localhost:1071/fuji/api/v1/ui/", timeout=5)
        return r.status_code == 200
    except:
        return False


if not check_server():
    print("❌ F-UJI server not running")
    exit(1)


# -----------------------------
# PROCESS EACH TOPIC FILE
# -----------------------------
subcloud_files = sorted(SUBCLOUD_DIR.glob("*.csv"))
if not subcloud_files:
    raise FileNotFoundError(f"No CSV files found in {SUBCLOUD_DIR}")

print(f"✅ Found {len(subcloud_files)} topic files in {SUBCLOUD_DIR}")

for sc_path in subcloud_files:
    topic = sc_path.stem
    sc_df = pd.read_csv(sc_path)
    datasets = sc_df["id"].dropna().astype(str).str.strip().tolist()

    print(f"\n{'='*55}")
    print(f"📂 Topic: {topic}  ({len(datasets)} datasets)")
    print(f"{'='*55}")

    results = []
    failed  = []
    is_first = True

    for i, dataset_id in enumerate(datasets):
        url = LOD_BASE_URL + dataset_id
        print(f"\n🔍 [{i+1}/{len(datasets)}] {dataset_id}")

        fair_result = evaluate_with_fuji(url, save_debug=is_first)
        is_first = False

        if fair_result:
            fair_result["id"] = dataset_id
            results.append(fair_result)
        else:
            failed.append({"id": dataset_id, "url": url})

        time.sleep(REQUEST_DELAY)

    # ── Save per-topic results ──────────────────────────────────────────────
    df_results = pd.DataFrame(results)
    df_failed  = pd.DataFrame(failed)

    if not df_results.empty:
        base_cols  = ["id", "url"]
        other_cols = [c for c in df_results.columns if c not in base_cols]
        df_results = df_results[base_cols + sorted(other_cols)]

    df_results.to_csv(OUTPUT_DIR / f"{topic}.csv",        index=False, encoding="utf-8")
    df_failed.to_csv( OUTPUT_DIR / f"{topic}_failed.csv", index=False, encoding="utf-8")

    print(f"\n  ✔ Success: {len(df_results)}  |  ❌ Failed: {len(df_failed)}")
    print(f"  📁 Saved → {OUTPUT_DIR / topic}.csv")


print("\n" + "=" * 55)
print("✅ All topics processed!")
print(f"📁 Results in: {OUTPUT_DIR}")
print("=" * 55)