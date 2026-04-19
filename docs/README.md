# FAIR Assessment Pipeline for LOD Cloud Knowledge Graphs

An automated pipeline for evaluating the FAIRness of Knowledge Graph datasets drawn from the [LOD Cloud](https://lod-cloud.net/), using three complementary tools: **KGHeartbeat**, **F-UJI**, and **FAIR-Checker**.

---

## Overview

This project measures how *Findable, Accessible, Interoperable, and Reusable* (FAIR) a curated set of LOD Cloud Knowledge Graph datasets are. Starting from a structured topic-based catalogue, it partitions datasets into sub-clouds and runs each one through three independent FAIRness evaluation frameworks, producing per-topic score tables ready for analysis or comparison.

**Three assessment tools are used:**

| Tool | Type | What it measures |
|---|---|---|
| [KGHeartbeat](https://github.com/your-org/kgheartbeat) | Baseline / expert | Pre-computed KG quality scores used as ground truth for merging |
| [F-UJI](https://github.com/pangaea-data-publisher/fuji) | Local REST server | FAIRsFAIR metrics (17+ tests across F-A-I-R) |
| [FAIR-Checker](https://fair-checker.france-bioinformatique.fr) | Remote API | Independent metric suite with per-principle aggregates |

---

## Repository Structure

```
project-root/
├── main.py                          # Single entrypoint — runs all steps
├── requirements.txt
│
├── src/
│   ├── LODCloudassment/
│   │   ├── LODsubcloudclasscsv.py   # Step 1 — generate per-topic CSVs
│   │   ├── LODsubcloudclassjson.py  # Step 2 — generate per-topic JSONs
│   │   └── mergefairscore.py        # Step 3 — merge with KGHeartbeat baseline
│   ├── F-UJI assessment/
│   │   ├── fujiass.py               # Step 4 — F-UJI batch assessment
│   │   └── fuji-master/             # F-UJI server source (submodule)
│   └── FAIR-checker/
│       └── FAIR-Checkerass.py       # Step 5 — FAIR-Checker batch assessment
│
└── data/
    ├── LODsubclouds/                 # Input CSVs for steps 4 & 5
    └── ass/
        ├── KGHBeatassessmentResult/
        │   ├── FAIRASSInput/         # kgs_by_topic.json + KGHeartbeat baseline CSV
        │   ├── LODsubclouds/         # JSON output of step 2
        │   └── FAIRASSout/           # Merged output of step 3
        ├── F-UJIassessmentResult/    # CSV output of step 4
        └── FAIR-CheckerassessmentResult/  # CSV output of step 5
```

---

## Pipeline Steps

The pipeline runs five steps in order. Each step is an independent Python module; `main.py` orchestrates them.

### Step 1 — Generate per-topic CSV files
**`src/LODCloudassment/LODsubcloudclasscsv.py`**

Reads `kgs_by_topic.json` (a mapping of topic names → LOD Cloud dataset URLs) and writes one `<topic>.csv` per topic into `data/LODsubclouds/`. Each CSV contains the extracted dataset IDs (the final path segment of each URL).

### Step 2 — Generate per-topic JSON files
**`src/LODCloudassment/LODsubcloudclassjson.py`**

Same source file as Step 1, but writes structured JSON objects (with topic name, count, and id list) plus a `_index.json` summary of all topic sizes.

### Step 3 — Merge with KGHeartbeat baseline
**`src/LODCloudassment/mergefairscore.py`**

Left-joins each sub-cloud CSV against the KGHeartbeat expert assessment baseline (a wide CSV keyed on `KG id`). The merged files — one per topic — are saved to `FAIRASSout/`. Datasets absent from the baseline keep all sub-cloud columns with NaN for the baseline fields.

### Step 4 — F-UJI automated assessment
**`src/F-UJI assessment/fujiass.py`**

For every dataset ID in every sub-cloud CSV, constructs the LOD Cloud landing URL and sends a POST request to a locally running F-UJI server (`localhost:1071`). Flattens the nested JSON response — summary scores, per-metric scores (earned / total / maturity), and per-test scores — into a single wide CSV row. Outputs `<topic>.csv` and `<topic>_failed.csv` per topic.

> **Requires a running F-UJI server.** The script checks the server on startup and exits early with a clear error if it is not reachable.

### Step 5 — FAIR-Checker assessment
**`src/FAIR-checker/FAIR-Checkerass.py`**

Calls the public FAIR-Checker REST API for each dataset URL. Applies URL pre-processing (Bio2RDF redirects, BioPortal path rewriting, blocked-domain filtering) before the request. Aggregates the returned per-metric scores into principle totals and averages (F / A / I / R) plus an overall score. Results and failures are saved per topic.

---

## Assessment Tools

### KGHeartbeat
KGHeartbeat is a Knowledge Graph quality assessment tool that produces a comprehensive set of quality indicators for LOD Cloud KGs. In this pipeline it acts as the **baseline**: its pre-computed results (stored in `FAIRASSInput/`) are merged into every sub-cloud file so that automated FAIR scores can be compared against expert-assessed quality metrics.

### F-UJI (FAIRsFAIR Data Object Assessment Service)
[F-UJI](https://www.f-uji.net) is a web service that programmatically assesses FAIRness based on metrics developed by the [FAIRsFAIR](https://www.fairsfair.eu/) project. It evaluates 17+ metrics spanning all four FAIR principles and returns granular per-test scores.

- Runs locally as a Python REST server on port `1071`
- Authenticated with username/password (`marvel` / `wonderwoman` by default — configure in `fuji_server/config/users.py`)
- Source included under `src/F-UJI assessment/fuji-master/`

**Reference:** Devaraju, A. and Huber, R. (2021). *An automated solution for measuring the progress toward FAIR research data.* Patterns, 2(11). https://doi.org/10.1016/j.patter.2021.100370

### FAIR-Checker
[FAIR-Checker](https://fair-checker.france-bioinformatique.fr) is a publicly accessible API hosted by France Bioinformatique. It applies its own independent metric suite and returns per-metric scores alongside recommendations and comments. No local installation is required.

- Accessed over HTTPS with a configurable timeout (default: 60 s) and request delay (default: 2 s)
- URL pre-processing handles known edge cases (Bio2RDF, BioPortal, blocked domains)

---

## Outputs

| Path | Content |
|---|---|
| `data/ass/F-UJIassessmentResult/<topic>.csv` | Flattened F-UJI scores per dataset (summary + per-metric + per-test) |
| `data/ass/F-UJIassessmentResult/<topic>_failed.csv` | Datasets that could not be assessed by F-UJI, with error reason |
| `data/ass/FAIR-CheckerassessmentResult/<topic>.csv` | FAIR-Checker scores per dataset with F/A/I/R aggregates |
| `data/ass/FAIR-CheckerassessmentResult/<topic>_failed.csv` | Datasets that could not be assessed by FAIR-Checker, with error reason |
| `data/ass/KGHBeatassessmentResult/FAIRASSout/<topic>.csv` | Sub-cloud datasets merged with KGHeartbeat baseline annotations |
| `data/ass/KGHBeatassessmentResult/LODsubclouds/<topic>.json` | Structured JSON topic files with id lists and counts |

---

## Requirements

- Python 3.11
- A locally running F-UJI server (for Step 4)
- Internet access to the FAIR-Checker API (for Step 5)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the F-UJI server (required for step 4)
cd "src/F-UJI assessment/fuji-master"
python -m fuji_server -c fuji_server/config/server.ini

# 3. Run the full pipeline
python main.py

# Run specific steps only
python main.py --steps 1,2          # generate sub-cloud files only
python main.py --steps 3            # merge with KGHeartbeat baseline only
python main.py --steps 4            # F-UJI assessment only
python main.py --steps 5            # FAIR-Checker assessment only
python main.py --steps 4,5          # both assessments (skip preprocessing)

# Abort immediately if any step fails
python main.py --stop-on-error
```

### Required input files

Before running, ensure the following files exist under `data/ass/KGHBeatassessmentResult/FAIRASSInput/`:

| File | Description |
|---|---|
| `kgs_by_topic.json` | Topic → list of LOD Cloud dataset URLs |
| `2025-04-27.csv` (or latest date) | KGHeartbeat baseline assessment results, keyed on `KG id` |

> Update the `FAIR_FILE` path in `fujiass.py` and `mergefairscore.py` if the baseline CSV filename changes.

---

## Configuration

| Setting | Location | Default |
|---|---|---|
| F-UJI server URL | `fujiass.py` → `FUJI_API` | `http://localhost:1071/fuji/api/v1/evaluate` |
| F-UJI credentials | `fujiass.py` → `FUJI_USER` / `FUJI_PASSWORD` | `marvel` / `wonderwoman` |
| F-UJI request delay | `fujiass.py` → `REQUEST_DELAY` | `3` seconds |
| FAIR-Checker API URL | `FAIR-Checkerass.py` → `API_URL` | `https://fair-checker.france-bioinformatique.fr` |
| FAIR-Checker request delay | `FAIR-Checkerass.py` → `REQUEST_DELAY` | `2` seconds |

---

## License

This project is licensed under the MIT License. The included F-UJI server (`fuji-master/`) is also MIT licensed — see [`src/F-UJI assessment/fuji-master/fuji-master/LICENSE`](src/F-UJI%20assessment/fuji-master/fuji-master/LICENSE).
