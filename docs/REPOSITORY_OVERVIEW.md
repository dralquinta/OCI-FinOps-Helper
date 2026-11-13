# OCI FinOps Helper — Repository Overview

A thorough explanation of what this repository does, how it works internally, what it produces, and how the pieces fit together. It is based on reading the code (`collector.sh`, `src/collector.py`, `src/utils/*.py`), the notebooks in `jupe-note/`, and the existing docs.

---

## 1. What the repo is

**OCI FinOps Helper** is a command-line data-collection toolkit (version 2.2.1 in the code) for Oracle Cloud Infrastructure (OCI). Given a tenancy OCID, a home region and a date range, it extracts everything needed to do a FinOps / cost-optimization review of that tenancy and writes it to local files:

1. **Cost and usage data**, daily and per resource, from the OCI Usage API.
2. **Resource metadata** that the Usage API does not provide: the compute instance *shape* and *display name*.
3. **Cost-saving recommendations** from Oracle Cloud Advisor (the Optimizer service), turned into a readable action report with ready-to-run CLI commands.
4. **"Growth" data**: tagging structure and compliance, tag-based cost breakdowns, performance metrics, audit events and event rules.
5. **Jupyter notebooks** that analyze the produced CSV/JSON files: cost trends, anomalies, forecasts, Exadata analysis and growth or sales-opportunity analysis.

It is a read-only tool. It queries and aggregates, and it never changes anything in the tenancy. The recommendation report only *prints* CLI commands the user may choose to run.

It is a community tool, not an officially supported Oracle product. It is licensed under UPL 1.0 and the files carry Oracle copyright headers.

### Who it is for

- FinOps practitioners and cloud cost analysts who need a clean, enriched cost dataset.
- OCI account teams and solution architects doing customer cost reviews. The notebook `growth_trends_analysis.ipynb` is framed around "what to sell and where", cross-sell and upsell.
- Cloud admins who want tagging governance reports and Cloud Advisor recommendations in one place.

---

## 2. Repository layout

```
OCI-FinOps-Helper/
├── collector.sh                  # Entry point: bash wrapper (auth check, venv, run python)
├── requirements.txt              # pandas, numpy, requests, matplotlib, seaborn, scikit-learn, jupyter
├── README.md                     # Usage guide
├── LICENSE                       # UPL 1.0
├── src/
│   ├── collector.py              # OCICostCollector: orchestration + CLI argument parsing
│   └── utils/
│       ├── api_executor.py       # Calls the Usage API via `oci raw-request`
│       ├── executor.py           # Parallel `oci compute instance get` (thread pool)
│       ├── recommendations.py    # Cloud Advisor fetch + human-readable report builder
│       ├── growth_collector.py   # Tags, metrics, audit events, event rules (largest module)
│       └── progress.py           # Spinner and progress-bar helpers
├── jupe-note/
│   ├── finops_analysis.ipynb         # General FinOps analysis of output_merged.csv
│   ├── exadata_analysis.ipynb        # Exadata / Database deep-dive
│   └── growth_trends_analysis.ipynb  # Growth, cross-sell and upsell analysis
└── docs/                         # Documentation (this file plus feature-specific docs, see §10)
```

---

## 3. High-level architecture

```
./collector.sh <tenancy> <region> <from> <to> [flags]
        │
        ▼
 collector.sh (bash)
   • checks that args are present
   • `oci iam region list` to verify authentication
   • creates ./venv, pip installs requirements.txt
   • runs: python3 src/collector.py "$@"
        │
        ▼
 src/collector.py  →  OCICostCollector
        │
        ├── OCIAPIExecutor        ── `oci raw-request` ──▶ Usage API  (COST, then USAGE)
        ├── pandas merge          ── join the two result sets
        ├── OCIMetadataFetcher    ── `oci compute instance get` × N (30 threads)
        ├── OCIGrowthCollector    ── iam / usage / monitoring / audit / events (optional)
        └── OCIRecommendationsFetcher ── `oci optimizer recommendation-summary list`
        │
        ▼
 ./output/   (CSV, JSON, text reports)  ──▶  Jupyter notebooks in jupe-note/
```

### Key design choices

- **The tool shells out to the OCI CLI** (`subprocess.run(['oci', ...])`) instead of using the OCI Python SDK. Authentication is therefore whatever the CLI is configured with: instance principal in OCI Cloud Shell, `~/.oci/config` API keys, or a security token session. The code prints hints for `--auth security_token` when a call fails. This keeps the Python free of credential handling.
- **Bash wrapper plus Python core.** The wrapper owns the environment (venv, auth check). The Python owns the logic.
- **Parallelism where it matters.** Per-instance lookups use 30 worker threads, and per-compartment scans (tag defaults, audit events, event rules) use thread pools (defaults 20 and 30 workers).
- **Graceful degradation.** Failures in enrichment, in growth collection and in recommendations are caught and reported, and the run continues. Only failure of the COST or USAGE call, or of the merge, aborts the run.

---

## 4. The entry point: `collector.sh`

Usage:

```bash
./collector.sh <tenancy_ocid> <home_region> <from_date> <to_date> [OPTIONS]
```

| Argument | Meaning |
|---|---|
| `tenancy_ocid` | OCID of the tenancy (`ocid1.tenancy.oc1..…`) |
| `home_region` | Tenancy home region, e.g. `us-ashburn-1` (the Usage API endpoint is regional: `https://usageapi.<region>.oci.oraclecloud.com/20200107/usage`) |
| `from_date`, `to_date` | `YYYY-MM-DD`. They are sent as `…T00:00:00Z` and the Usage API treats the end as exclusive. |

Flags:

| Flag | Effect |
|---|---|
| *(none)* | Cost + usage + instance enrichment + recommendations |
| `--only-recommendations` | Fetch only Cloud Advisor recommendations (seconds) |
| `--growth-collection` | Full run, plus tag/growth collection and tag enrichment of the CSV |
| `--only-growth` | Intended to run only growth collection (see the known issue in §9) |
| `--currency <CODE>` | Currency label used in the recommendation report (default `USD`) |
| `--skip-cost`, `--skip-usage` | Skip one of the two Usage API calls |
| `--skip-enrichment` | Skip instance metadata enrichment (see §9) |
| `--skip-recommendations` | Skip Cloud Advisor |

What the wrapper does, step by step:

1. Requires at least four arguments, otherwise prints usage and exits 1.
2. `check_oci_auth`: runs `oci iam region list`. If it fails, it stops.
3. `setup_venv`: creates `venv/` next to the script if missing, activates it, upgrades pip and installs `requirements.txt`.
4. `run_collector`: activates the venv and runs `python3 src/collector.py "$@"`.
5. Prints the list of output files.

---

## 5. The pipeline in detail

### 5.1 Step 1: COST query

`OCIAPIExecutor.make_api_call` builds a request body, saves it to `output/request_<name>.json`, and POSTs it with `oci raw-request` (300 s timeout):

```json
{
  "tenantId": "<tenancy>",
  "timeUsageStarted": "<from>T00:00:00Z",
  "timeUsageEnded":   "<to>T00:00:00Z",
  "granularity": "DAILY",
  "queryType": "COST",
  "groupBy": ["service", "skuName", "resourceId", "compartmentPath"],
  "compartmentDepth": 4
}
```

This yields daily cost rows (`computedAmount`, `computedQuantity`, `currency`, …) per service, SKU, resource and compartment path.

### 5.2 Step 2: USAGE query

Same request with `queryType: "USAGE"` and `groupBy: ["resourceId", "platform", "region", "skuPartNumber"]`.

**Why two calls?** The Usage API allows at most **4 `groupBy` keys** per query and only a fixed list of keys. The desired fields do not fit in one query, so the tool makes two queries and joins them. `shape` and `resourceName` are not valid groupBy keys at all, so they must come from the Compute API.

### 5.3 Step 3: merge

In `OCICostCollector.merge_and_enrich`:

- Saves both raw responses to `output/out.json` (`{"call1": …, "call2": …}`).
- Loads each response's `items` into a pandas DataFrame.
- Builds a composite key `resourceId + "_" + timeUsageStarted` in both frames.
- **Left-joins** the USAGE columns (`platform`, `region`, `skuPartNumber`, plus `shape` and `resourceName` if present) onto the COST frame. COST rows are the master dataset.
- Writes the un-enriched result to `output/output.csv`.

### 5.4 Step 4–5: compute instance enrichment

- Finds unique `resourceId`s containing `instance.oc1` (compute instances).
- `OCIMetadataFetcher` (30 threads) parses the region out of each OCID (`ocid1.instance.oc1.<region>.<id>`) and runs `oci compute instance get --instance-id … --region <region>`, reading `shape` and `display-name`.
- Results are written to `output/instance_metadata.json`.
- Missing `shape`/`resourceName` values in the merged frame are filled in. Existing values are never overwritten.
- Terminated instances typically cannot be fetched. These are counted as failures and are expected.
- The result is saved as `output/output_merged.csv`, the main analytical dataset.

### 5.5 Step 6: growth collection (optional, `--growth-collection`)

Implemented by `OCIGrowthCollector.collect_all`. It collects:

| Data | How |
|---|---|
| Compartments | `oci iam compartment list` (whole tenancy subtree) |
| Tag namespaces | `oci iam tag-namespace list` |
| Tag definitions | `oci iam tag list`, per namespace, in parallel |
| Tag defaults (auto-tagging rules) | `oci iam tag-default list`, per compartment, in parallel |
| Resource tags | Usage API `USAGE` grouped by `resourceId, tagNamespace, tagKey, tagValue`. Builds a per-resource tag map and statistics on unique namespaces, keys and values. |
| Cost-tracking tags | Usage API `COST` grouped by tag keys, giving cost per tag combination |
| Performance metrics | Monitoring `summarizeMetricsData` for CPU/memory (compute), volume throughput, VNIC network bytes, DB CPU/storage and connections. The query is `<Metric>[1m].mean()`. |
| Audit events | `oci audit event list` per compartment, in parallel. Summarizes event types, resource types, users and compartments. |
| Event rules | `oci events rule list` per compartment, in parallel: enabled/disabled counts and action types. |

Outputs: `growth_collection_tags.json` (full data) and `growth_collection_summary.txt` (readable summary).

Then `enrich_dataframe_with_tags` adds columns to the cost dataframe and re-saves `output_merged.csv`:

- `has_tags`, `tag_count`, `tag_namespaces`
- `tags` (JSON list of tags)
- `primary_cost_center`, taken from tag keys such as `costcenter`, `cost-center`, `cost_center`, `department`
- `primary_environment`, taken from keys such as `environment`, `env`, `stage`

### 5.6 Step 7: Cloud Advisor recommendations

`OCIRecommendationsFetcher`:

- Runs `oci optimizer recommendation-summary list --compartment-id <tenancy> --compartment-id-in-subtree true --region <region> --all`.
- Saves the raw JSON to `recommendations.json`.
- Builds `recommendations.out`, a report with:
  - an **executive summary** (total estimated monthly savings, number of recommendations, critical/high counts);
  - **savings by category**, with friendly names such as "Boot Volumes - Optimize size and performance settings" or "Compute Commitments - Purchase 1-3 year commitments for discounts";
  - per recommendation: **priority**, **savings**, **"What this means"**, **"Actions to take"** and a **"CLI command to execute"**.
- The CLI commands are generated by keyword mapping of the recommendation name: right-size a compute shape, delete unattached or terminated-instance boot volumes, stop idle compute, review load balancers, Autonomous DB scaling, Object Storage lifecycle policies, replication and bucket tier changes, DB system CPU changes, volume auto-tune and more. They fall back to `oci optimizer recommendation get`. The report also points to `oci optimizer recommendation bulk-apply`.

This step is independent of the cost data, which is why `--only-recommendations` finishes in seconds.

---

## 6. Output files

All files go to `./output/` (relative to the current working directory; it is gitignored).

| File | Produced when | Content |
|---|---|---|
| `output_merged.csv` | cost + usage | **Main dataset**: cost + usage + shape/name (+ tag columns if growth was run) |
| `output.csv` | cost + usage | Merged data before instance enrichment |
| `out.json` | cost + usage | Raw COST and USAGE API responses |
| `instance_metadata.json` | instances found | `resourceId → {shape, resourceName}` |
| `request_*.json` | any API call | Request bodies sent (debugging) |
| `recommendations.out` | recommendations | Human-readable action report |
| `recommendations.json` | recommendations | Raw Cloud Advisor data |
| `growth_collection_tags.json` | growth | All tag, metrics, audit and event data |
| `growth_collection_summary.txt` | growth | Readable summary of the above |

Note: the README mentions `output.json` in places. The code actually writes **`out.json`**.

Typical columns of `output_merged.csv`: `service`, `skuName`, `skuPartNumber`, `resourceId`, `resourceName`, `shape`, `compartmentPath`, `compartmentName`, `compartmentId`, `platform`, `region`, `computedAmount`, `computedQuantity`, `currency`, `timeUsageStarted`, `timeUsageEnded`, and optionally the tag columns.

---

## 7. The analysis notebooks (`jupe-note/`)

These consume `output_merged.csv` and are where the data turns into insight. The extra dependencies in `requirements.txt` (matplotlib, seaborn, scikit-learn, jupyter) exist for them.

- **`finops_analysis.ipynb`** (about 46 cells). General FinOps report:
  - cleaning and preparation;
  - tag coverage, cost-center and environment analysis;
  - an executive summary of key metrics;
  - cost by service, region and compartment;
  - daily trends and service distribution over time;
  - compute, storage and database deep dives, and top resource consumers;
  - **anomaly detection**;
  - cost-optimization opportunities;
  - a simple linear forecast;
  - CSV export of insights and a free-form query section.
- **`exadata_analysis.ipynb`**. Exadata and Database infrastructure: filtering, SKU analysis (infrastructure vs CPU cost by date), separate and combined Exadata/DB cost analysis, report export, forecasting and anomalies.
- **`growth_trends_analysis.ipynb`**. Framed as "growth trends and sales planning":
  - time-series growth rates and high-growth services;
  - regional and compartment analysis;
  - consumption forecasts;
  - **cross-selling** (services used together, adoption gaps), **upselling** (premium-tier upgrades) and a focus on the top 3 regions;
  - cost-tracking and tagging analysis, where untagged resources are treated as governance opportunities.

---

## 8. Prerequisites and permissions

- **OCI CLI** installed and authenticated (Cloud Shell instance principal, or `~/.oci/config`).
- **Python 3** with `venv` and `pip`. The venv is created automatically on first run.
- **IAM permissions**, read-only. The exact policies are in the growth and performance docs. They broadly cover:
  - usage reports (`read usage-reports in tenancy`);
  - reading compute instances;
  - inspect/read tag namespaces and tag defaults, and inspect compartments;
  - read metrics and audit events (for the growth/performance data);
  - Cloud Advisor / Optimizer access (without it the recommendations step only warns).

---

## 9. Behavior notes and known issues (observed in the code)

These are things worth knowing before relying on the tool. They come from reading the code, not from running it.

1. **`--only-growth` appears not to run growth collection.** In `OCICostCollector.collect`, growth collection is nested inside the `if not (skip_cost or skip_usage)` merge block. `--only-growth` sets `skip_cost=True` and `skip_usage=True`, so that block is skipped and no growth data is written. It also skips recommendations. In practice, `--growth-collection` on a full run is the working path. This contradicts the README and `docs/GROWTH_COLLECTION.md`.
2. **`--skip-enrichment` does not skip enrichment.** It only prints a message and then calls `merge_and_enrich`, which still performs the instance lookups.
3. **Skipping only one of cost or usage disables the merge.** If either call is skipped, `merge_and_enrich` is not invoked, so no `output_merged.csv` is produced. The skipped-stage flags are mainly useful together with `--only-recommendations`.
4. **Unmatched merge rows.** The join is a left join on `resourceId + timeUsageStarted`, so USAGE-only rows are dropped. The USAGE query does not return `shape` or `resourceName`, so those columns come only from the Compute enrichment.
5. **Only compute instances are enriched** (`instance.oc1`). Other resource types keep empty `shape` and `resourceName`.
6. **Large runs are slow.** One CLI call per instance, one per compartment for tags/audit/events, and audit and metrics scans can be heavy on big tenancies. The README estimates minutes for a month of data and 30+ minutes for 3+ months.
7. **Docs vs code drift.** The README mentions `output.json`, while the code writes `out.json`. The README directory tree names the folder `cost_report/` and does not list `growth_collector.py` or the notebooks. `docs/CHANGELOG.md` calls the growth feature "v2.1", while the code and wrapper say v2.2.1. The growth module also gained metrics, audit and event-rule collection beyond what the README table lists.

---

## 10. Other documentation in `docs/`

| File | Topic |
|---|---|
| `ARCHITECTURE.md` | Original system design, data flow, API request/response shapes (written before growth collection) |
| `QUICK_REFERENCE.md` | Common commands and usage patterns |
| `CHANGELOG.md` | Version history |
| `RECOMMENDATIONS.md`, `RECOMMENDATIONS_QUICK_REFERENCE.md`, `INDEX_RECOMMENDATIONS.md`, `GET_STARTED_RECOMMENDATIONS.md` | Cloud Advisor recommendations feature |
| `V2.1_NEW_FEATURES.md` | v2.1 feature notes |
| `GROWTH_COLLECTION*.md` | Tag/growth collection guide, implementation, performance and quick reference |
| `PERFORMANCE_AND_AUDIT_COLLECTION.md` | Monitoring metrics and audit event collection |
| `IMPLEMENTATION_SUMMARY.md` | Summary of recent enhancements |

---

## 11. Quick start

```bash
# Full collection for November 2025
./collector.sh ocid1.tenancy.oc1..<id> us-ashburn-1 2025-11-01 2025-12-01

# Full collection plus tag/growth analysis and tag-enriched CSV
./collector.sh ocid1.tenancy.oc1..<id> us-ashburn-1 2025-11-01 2025-12-01 --growth-collection

# Recommendations only (fast)
./collector.sh ocid1.tenancy.oc1..<id> us-ashburn-1 2025-11-01 2025-12-01 --only-recommendations --currency EUR

# Then analyze
cd jupe-note && jupyter notebook finops_analysis.ipynb   # loads output/output_merged.csv
```

---

## 12. Summary

The repository automates the tedious first half of an OCI FinOps engagement: pulling daily cost and usage from the Usage API (working around its 4-key `groupBy` limit with two queries and a merge), enriching it with compute shape and name, optionally adding tagging, metrics, audit and event data, and capturing Cloud Advisor savings recommendations with ready-to-run commands. The second half, turning that data into trends, anomalies, forecasts and cross-sell/upsell insights, is done in the three Jupyter notebooks. It runs anywhere the OCI CLI is authenticated, with OCI Cloud Shell as the easiest path.
