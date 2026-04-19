#!/usr/bin/env python3

import requests
import pandas as pd
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse


# ─────────────────────────────────────────────
# JSON-LD PROPERTY CONSTANTS
# ─────────────────────────────────────────────
DQV_VALUE       = "http://www.w3.org/ns/dqv#value"
DQV_MEASUREMENT = "http://www.w3.org/ns/dqv#QualityMeasurement"
DQV_IN_METRIC   = "http://www.w3.org/ns/dqv#isMeasurementOf"
DQV_IN_CATEGORY = "http://www.w3.org/ns/dqv#inCategory"
SCHEMA_MAX      = "http://schema.org/maxValue"
SCHEMA_VALUE    = "http://schema.org/value"
SCHEMA_DESC     = "http://schema.org/description"
RDFS_COMMENT    = "http://www.w3.org/2000/01/rdf-schema#comment"
DCTERMS_DESC    = "http://purl.org/dc/terms/description"

# ─────────────────────────────────────────────
# STANDARD FAIR METRICS (15 total)
# ─────────────────────────────────────────────
FAIR_METRICS: List[str] = [
    "F1A", "F1B", "F2", "F3", "F4",
    "A1.1", "A1.2", "A2",
    "I1", "I2", "I3",
    "R1.1", "R1.2", "R1.3", "R1.4",
]

METRIC_ALIASES: Dict[str, str] = {
    "F1":  "F1A",
    "A11": "A1.1",
    "A12": "A1.2",
    "R11": "R1.1",
    "R12": "R1.2",
    "R13": "R1.3",
    "R14": "R1.4",
}


class FAIRAssessment:
    def __init__(self, input_file: str = "input.csv",
                 output_file: str = "fair_results.csv"):
        self.input_file       = input_file
        self.output_file      = output_file
        self.api_url          = "https://fair-checker.france-bioinformatique.fr"
        self.session          = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
        self.request_timeout  = 60
        self.working_method   = None
        self.working_endpoint = None

    # ─────────────────────────────────────────────
    # API PROBE
    # ─────────────────────────────────────────────
    def probe_api(self) -> bool:
        test_url = "https://doi.org/10.1594/PANGAEA.908011"

        candidates: List[Tuple[str, str]] = [
            ("GET",  f"{self.api_url}/api/check/metrics_all"),
            ("GET",  f"{self.api_url}/api/check/metric_F1"),
            ("POST", f"{self.api_url}/api/check/metrics_all"),
        ]

        print("\n── API PROBE ─────────────────────────────")

        for method, endpoint in candidates:
            try:
                if method == "GET":
                    r = self.session.get(endpoint, params={"url": test_url}, timeout=15)
                else:
                    r = self.session.post(endpoint, json={"url": test_url}, timeout=15)

                print(f"{method} {endpoint} → {r.status_code}")

                if r.status_code == 200:
                    self.working_method   = method
                    self.working_endpoint = endpoint
                    print("✓ Working endpoint found\n")
                    return True

            except Exception as e:
                print("Error:", e)

        return False

    # ─────────────────────────────────────────────
    # LOAD DATA
    # ─────────────────────────────────────────────
    def load_datasets(self) -> pd.DataFrame:
        df = pd.read_csv(self.input_file)

        required = {'id', 'title', 'url'}
        if not required.issubset(df.columns):
            raise ValueError(f"Missing columns: {required - set(df.columns)}")

        df['url'] = df['url'].astype(str).str.strip()

        # Only drop rows where url is completely empty / NaN
        df = df[df['url'].notna() & (df['url'] != '') & (df['url'] != 'nan')]
        df = df.reset_index(drop=True)
        return df

    # ─────────────────────────────────────────────
    # JSON-LD HELPERS
    # ─────────────────────────────────────────────
    def _get_value(self, node: dict, prop: str) -> Optional[float]:
        raw = node.get(prop)
        if raw is None:
            return None
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "@value" in item:
                    try:
                        return float(item["@value"])
                    except (TypeError, ValueError):
                        continue
                try:
                    return float(item)
                except (TypeError, ValueError):
                    continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _get_str(self, node: dict, *props: str) -> str:
        for prop in props:
            raw = node.get(prop)
            if raw is None:
                continue
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        v = item.get("@value") or item.get("@id") or ""
                        if v:
                            return str(v).strip()
                    if item:
                        return str(item).strip()
            if raw:
                return str(raw).strip()
        return ""

    def _normalise_metric(self, raw: str) -> str:
        cleaned = raw.strip().upper()
        return METRIC_ALIASES.get(cleaned, cleaned)

    def _graph_nodes(self, data) -> List[dict]:
        if isinstance(data, dict):
            data = data.get("@graph", data.get("results", [data]))
        if isinstance(data, list):
            return [n for n in data if isinstance(n, dict)]
        return []

    def _metric_id_from_node(self, node: dict) -> Optional[str]:
        ref = node.get(DQV_IN_METRIC)
        if ref is None:
            return None
        if isinstance(ref, list):
            ref = ref[0] if ref else None
        if isinstance(ref, dict):
            uri = ref.get("@id", "")
        else:
            uri = str(ref)
        if not uri:
            return None
        segment = uri.rstrip("/").split("/")[-1]
        segment = segment.replace("RDA-", "").replace("rda-", "")
        return self._normalise_metric(segment)

    # ─────────────────────────────────────────────
    # FLAT SCORES — same columns as legacy script
    # ─────────────────────────────────────────────
    def _build_flat_scores(self, data) -> Dict:
        flat: Dict = {}
        for m in FAIR_METRICS:
            flat[f"score_{m}"]          = None
            flat[f"recommendation_{m}"] = ""
            flat[f"comment_{m}"]        = ""

        principle_buckets: Dict[str, List[float]] = {
            "F": [], "A": [], "I": [], "R": []
        }
        all_scores: List[float] = []

        for node in self._graph_nodes(data):
            node_types = node.get("@type", [])
            if isinstance(node_types, str):
                node_types = [node_types]
            if DQV_MEASUREMENT not in node_types:
                continue

            metric = self._metric_id_from_node(node)
            if not metric:
                continue

            score = self._get_value(node, DQV_VALUE)
            if score is None:
                score = self._get_value(node, SCHEMA_VALUE)

            recommendation = self._get_str(node, SCHEMA_DESC, RDFS_COMMENT, DCTERMS_DESC)
            comment        = self._get_str(node, "http://www.w3.org/2004/02/skos/core#note")

            flat[f"score_{metric}"]          = score
            flat[f"recommendation_{metric}"] = recommendation
            flat[f"comment_{metric}"]        = comment

            if score is not None:
                all_scores.append(score)
                principle = metric[0].upper()
                if principle in principle_buckets:
                    principle_buckets[principle].append(score)

        # Per-principle aggregates
        for p, scores in principle_buckets.items():
            if scores:
                flat[f"total_{p}"] = round(sum(scores), 4)
                flat[f"avg_{p}"]   = round(sum(scores) / len(scores), 3)
            else:
                flat[f"total_{p}"] = None
                flat[f"avg_{p}"]   = None

        # Overall aggregates
        if all_scores:
            flat["score_total"]       = round(sum(all_scores), 4)
            flat["score_avg"]         = round(sum(all_scores) / len(all_scores), 3)
            flat["metrics_evaluated"] = len(all_scores)
        else:
            flat["score_total"]       = None
            flat["score_avg"]         = None
            flat["metrics_evaluated"] = 0

        return flat

    def _overall_pct(self, data) -> Optional[float]:
        achieved, maximums = [], []
        for node in self._graph_nodes(data):
            node_types = node.get("@type", [])
            if isinstance(node_types, str):
                node_types = [node_types]
            if DQV_MEASUREMENT not in node_types:
                continue
            val = self._get_value(node, DQV_VALUE)
            if val is None:
                val = self._get_value(node, SCHEMA_VALUE)
            if val is None:
                continue
            max_val = self._get_value(node, SCHEMA_MAX) or 1.0
            achieved.append(val)
            maximums.append(max_val)
        if not achieved:
            return None
        total_max = sum(maximums)
        return round(sum(achieved) / total_max * 100, 2) if total_max > 0 else 0.0

    # ─────────────────────────────────────────────
    # EMPTY FLAT ROW (for failed assessments)
    # ─────────────────────────────────────────────
    def _empty_flat(self) -> Dict:
        flat: Dict = {}
        for m in FAIR_METRICS:
            flat[f"score_{m}"]          = None
            flat[f"recommendation_{m}"] = ""
            flat[f"comment_{m}"]        = ""
        for p in ("F", "A", "I", "R"):
            flat[f"total_{p}"] = None
            flat[f"avg_{p}"]   = None
        flat["score_total"]       = None
        flat["score_avg"]         = None
        flat["metrics_evaluated"] = 0
        return flat

    # ─────────────────────────────────────────────
    # API CALL  — sends url AS-IS, no preprocessing
    # ─────────────────────────────────────────────
    def assess_url(self, url: str) -> Dict:
        try:
            if self.working_method == "GET":
                r = self.session.get(
                    self.working_endpoint,
                    params={"url": url},
                    timeout=self.request_timeout
                )
            else:
                r = self.session.post(
                    self.working_endpoint,
                    json={"url": url},
                    timeout=self.request_timeout
                )

            r.raise_for_status()
            data  = r.json()
            flat  = self._build_flat_scores(data)
            pct   = self._overall_pct(data)

            return {"success": True, "score_pct": pct, "error": "", **flat}

        except requests.exceptions.Timeout:
            return {"success": False, "score_pct": None,
                    "error": "Timeout", **self._empty_flat()}

        except requests.exceptions.HTTPError as e:
            return {"success": False, "score_pct": None,
                    "error": f"HTTP {e.response.status_code}", **self._empty_flat()}

        except Exception as e:
            return {"success": False, "score_pct": None,
                    "error": str(e), **self._empty_flat()}

    # ─────────────────────────────────────────────
    # COLUMN ORDER  (mirrors legacy script)
    # ─────────────────────────────────────────────
    @staticmethod
    def _column_order() -> List[str]:
        cols = ["id", "title", "url", "success", "error", "score_pct"]
        for m in FAIR_METRICS:
            cols.append(f"score_{m}")
        for m in FAIR_METRICS:
            cols.append(f"recommendation_{m}")
        for m in FAIR_METRICS:
            cols.append(f"comment_{m}")
        for p in ("F", "A", "I", "R"):
            cols += [f"total_{p}", f"avg_{p}"]
        cols += ["score_total", "score_avg", "metrics_evaluated"]
        return cols

    # ─────────────────────────────────────────────
    # RUN PIPELINE
    # ─────────────────────────────────────────────
    def run(self):
        print("Probing API...")
        if not self.probe_api():
            print("No working endpoint found")
            return

        df = self.load_datasets()
        total = len(df)
        print(f"Datasets to assess: {total}")
        print(f"Metrics tracked   : {', '.join(FAIR_METRICS)}\n")

        rows           = []
        success_count  = 0
        failed_count   = 0

        for i, row in df.iterrows():
            url = row["url"]
            print(f"[{i+1:>4}/{total}] {url}")

            result = self.assess_url(url)

            if result["success"]:
                success_count += 1
                print(f"         score_pct={result['score_pct']}%  "
                      f"total={result.get('score_total')}  "
                      f"avg={result.get('score_avg')}  "
                      f"metrics={result.get('metrics_evaluated')}")
            else:
                failed_count += 1
                print(f"         FAILED: {result['error']}")

            # Build flat CSV row — url used as-is, no processed_url column
            csv_row = {
                "id":        row.get("id", ""),
                "title":     row.get("title", ""),
                "url":       url,
                "success":   result["success"],
                "error":     result["error"],
                "score_pct": result["score_pct"],
            }
            # Append all score_* / recommendation_* / comment_* / total_* / avg_* keys
            for key, val in result.items():
                if key not in csv_row:
                    csv_row[key] = val

            rows.append(csv_row)
            time.sleep(1)

        # ── Save CSV ──────────────────────────────────────────────────────
        out_df  = pd.DataFrame(rows)
        ordered = self._column_order()
        present = [c for c in ordered if c in out_df.columns]
        extra   = [c for c in out_df.columns if c not in ordered]
        out_df  = out_df[present + extra]

        out_df.to_csv(self.output_file, index=False, encoding="utf-8")

        print(f"\n── Saved → {self.output_file}")
        print(f"   Rows: {len(out_df)}  |  Columns: {len(out_df.columns)}")

        # ── Final summary ─────────────────────────────────────────────────
        valid = [r for r in rows if r["success"] and r.get("score_pct") is not None]

        print("\n──────── SUMMARY ────────")
        print(f"Total   : {total}")
        print(f"Success : {success_count}")
        print(f"Failed  : {failed_count}")

        if valid:
            avg_pct = sum(r["score_pct"] for r in valid) / len(valid)
            print(f"Average FAIR score : {round(avg_pct, 2)}%")

            print("\nPer-principle averages:")
            for p in ("F", "A", "I", "R"):
                vals = [r[f"avg_{p}"] for r in valid if r.get(f"avg_{p}") is not None]
                if vals:
                    print(f"  {p}  avg={round(sum(vals)/len(vals), 3)}  (n={len(vals)})")

            print("\nPer-metric averages:")
            for m in FAIR_METRICS:
                vals = [r[f"score_{m}"] for r in valid
                        if r.get(f"score_{m}") is not None]
                if vals:
                    print(f"  {m:<8} avg={round(sum(vals)/len(vals), 3)}  n={len(vals)}")
                else:
                    print(f"  {m:<8} no data")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    FAIRAssessment("input.csv", "fair_results.csv").run()