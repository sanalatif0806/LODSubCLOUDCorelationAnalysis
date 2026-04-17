#!/usr/bin/env python3
import requests
import pandas as pd
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent.parent
SUBCLOUD_DIR = DATA_DIR / "data" / "LODsubclouds"
OUTPUT_DIR = DATA_DIR / "data" / "ass" / "FAIR-CheckerassessmentResult"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOD_BASE_URL = "https://lod-cloud.net/dataset/"
API_URL = "https://fair-checker.france-bioinformatique.fr"
REQUEST_DELAY = 2
TIMEOUT = 60

# ── URL helpers ───────────────────────────────────────────────────────────────
BLOCKED_DOMAINS = {
    "thermofisher.com", "wikipedia.org", "github.com", "example.com"
}
BLOCKED_PATHS = {"/about", "/contact", "/documentation", "/help"}


def is_assessable(url: str) -> bool:
    try:
        p = urlparse(url)
        if any(d in p.netloc for d in BLOCKED_DOMAINS):
            return False
        if any(p.path.lower().startswith(bp) for bp in BLOCKED_PATHS):
            return False
        return True
    except Exception:
        return False


def preprocess_url(url: str) -> Optional[str]:
    try:
        url = str(url).strip()
        if not is_assessable(url):
            return None

        p = urlparse(url)

        if "bio2rdf.org" in p.netloc and p.path.count("/") >= 2:
            ds = p.path.strip("/").split("/")[-1]
            return f"http://download.bio2rdf.org/release/3/{ds}/{ds}.nt"

        if "ontobee.org" in p.netloc:
            return "http://sparql.hegroup.org/sparql"

        if "bioportal.bioontology.org" in p.netloc:
            return f"http://data.bioontology.org/ontologies/{p.path.split('/')[-1]}"

        return url
    except Exception:
        return None


# ── HTTP session ──────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"Accept": "application/json"})


# ── Helper: safe score conversion ─────────────────────────────────────────────
def safe_float(value, dataset_id=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        if dataset_id:
            print(f"⚠️ Invalid score for {dataset_id}: {value}")
        return None


# ── API call ──────────────────────────────────────────────────────────────────
def assess_dataset(dataset_id: str, raw_url: str) -> Dict:
    # Guard clause for None or invalid dataset_id
    if dataset_id is None or (isinstance(dataset_id, str) and dataset_id.strip() == ''):
        return {
            "id": str(dataset_id) if dataset_id is not None else "unknown",
            "original_url": raw_url,
            "processed_url": None,
            "assessment_success": False,
            "error": "Invalid or empty dataset ID"
        }

    # Ensure dataset_id is string and strip it
    dataset_id = str(dataset_id).strip()

    processed_url = preprocess_url(raw_url)

    base = {
        "id": dataset_id,
        "original_url": raw_url,
        "processed_url": processed_url,
    }

    if not processed_url:
        return {**base, "assessment_success": False, "error": "URL filtered out"}

    try:
        resp = session.get(
            f"{API_URL}/api/check/legacy/metrics_all",
            params={"url": processed_url},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        flat_scores = {}

        if isinstance(data, list):

            principle_scores: Dict[str, List[float]] = {
                "F": [], "A": [], "I": [], "R": []
            }

            all_scores: List[float] = []

            for item in data:
                metric = item.get("metric", "").strip()
                raw_score = item.get("score")

                score = safe_float(raw_score, dataset_id)

                if metric:
                    flat_scores[f"score_{metric}"] = score
                    flat_scores[f"recommendation_{metric}"] = item.get("recommendation", "")
                    flat_scores[f"comment_{metric}"] = item.get("comment", "")

                if score is not None:
                    all_scores.append(score)

                    if metric:
                        principle = metric[0].upper()
                        if principle in principle_scores:
                            principle_scores[principle].append(score)

            # ── Aggregate per principle ───────────────────────────────────────
            for principle, scores in principle_scores.items():
                if scores:
                    total = sum(scores)
                    flat_scores[f"total_{principle}"] = total
                    flat_scores[f"avg_{principle}"] = round(total / len(scores), 3)

            # ── Overall aggregation ──────────────────────────────────────────
            if all_scores:
                total_all = sum(all_scores)
                flat_scores["score_total"] = total_all
                flat_scores["score_avg"] = round(total_all / len(all_scores), 3)
                flat_scores["metrics_evaluated"] = len(all_scores)

        else:
            flat_scores["raw_response"] = str(data)[:500]

        return {
            **base,
            "assessment_success": True,
            **flat_scores,
        }

    except requests.exceptions.Timeout:
        return {**base, "assessment_success": False, "error": "Timeout"}

    except requests.exceptions.HTTPError as e:
        return {
            **base,
            "assessment_success": False,
            "error": f"HTTP {e.response.status_code}",
        }

    except requests.exceptions.RequestException as e:
        return {**base, "assessment_success": False, "error": str(e)}

    except Exception as e:
        return {**base, "assessment_success": False, "error": f"Unexpected: {e}"}


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    subcloud_files = sorted(SUBCLOUD_DIR.glob("*.csv"))

    if not subcloud_files:
        raise FileNotFoundError(f"No CSV files found in {SUBCLOUD_DIR}")

    print(f"✅ Found {len(subcloud_files)} topic file(s)")
    print(f"📁 Results → {OUTPUT_DIR}\n")

    grand_success = 0
    grand_failed = 0

    for sc_path in subcloud_files:
        topic = sc_path.stem

        # Read CSV and properly filter out NaN/None values
        df = pd.read_csv(sc_path)

        # Check if 'id' column exists
        if 'id' not in df.columns:
            print(f"⚠️ No 'id' column found in {topic}. Skipping...")
            continue

        # Method 1: Use pandas to clean the data
        # Drop NaN values, convert to string, strip whitespace
        ids_series = df['id'].dropna()

        # Convert to string and strip
        ids_series = ids_series.astype(str).str.strip()

        # Filter out empty strings and 'nan' strings
        ids_series = ids_series[~ids_series.isin(['', 'nan', 'NaN', 'None'])]

        # Convert to list
        ids = ids_series.tolist()

        print(f"\n{'=' * 60}")
        print(f"📂 Topic: {topic}")
        print(f"   Total rows in CSV: {len(df)}")
        print(f"   Valid IDs found: {len(ids)}")
        if len(df) - len(ids) > 0:
            print(f"   Filtered out: {len(df) - len(ids)} invalid entries")
        print(f"{'=' * 60}")

        if not ids:
            print(f"⚠️ No valid dataset IDs found in {topic}. Skipping...")
            continue

        results = []
        failed = []

        for i, dataset_id in enumerate(ids, 1):
            # Extra safety check before processing
            if not dataset_id or dataset_id.lower() in ['nan', 'none', '']:
                failed.append({
                    "id": dataset_id,
                    "original_url": LOD_BASE_URL + str(dataset_id),
                    "processed_url": None,
                    "assessment_success": False,
                    "error": "Invalid dataset ID after filtering"
                })
                print(f"  ✗ [{i:>3}/{len(ids)}] {str(dataset_id)[:50]:<50} Invalid ID")
                continue

            url = LOD_BASE_URL + dataset_id
            result = assess_dataset(dataset_id, url)

            if result["assessment_success"]:
                results.append(result)
                print(
                    f"  ✓ [{i:>3}/{len(ids)}] {dataset_id[:50]:<50} "
                    f"total={result.get('score_total', '?')} "
                    f"avg={result.get('score_avg', '?')}"
                )
            else:
                failed.append(result)
                print(
                    f"  ✗ [{i:>3}/{len(ids)}] {dataset_id[:50]:<50} "
                    f"{result.get('error', 'Unknown error')}"
                )

            time.sleep(REQUEST_DELAY)

        # ── Save results ─────────────────────────────────────────────────────
        if results:
            df_ok = pd.DataFrame(results)
            ok_path = OUTPUT_DIR / f"{topic}.csv"
            df_ok.to_csv(ok_path, index=False, encoding="utf-8")
            print(f"\n  📄 Saved successful results ({len(results)}) to: {ok_path}")

        if failed:
            df_fail = pd.DataFrame(failed)
            fail_path = OUTPUT_DIR / f"{topic}_failed.csv"
            df_fail.to_csv(fail_path, index=False, encoding="utf-8")
            print(f"  📄 Saved failed results ({len(failed)}) to: {fail_path}")

        grand_success += len(results)
        grand_failed += len(failed)

        print(f"\n  ✔ Success: {len(results)}")
        print(f"  ✗ Failed : {len(failed)}")
        print(f"  📊 Success rate: {(len(results) / (len(results) + len(failed)) * 100):.1f}%")

    # ── Final summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("✅ ALL TOPICS COMPLETE")
    print(f"Total datasets processed: {grand_success + grand_failed}")
    print(f"Total successful: {grand_success}")
    print(f"Total failed: {grand_failed}")
    if (grand_success + grand_failed) > 0:
        print(f"Overall success rate: {(grand_success / (grand_success + grand_failed) * 100):.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    run()