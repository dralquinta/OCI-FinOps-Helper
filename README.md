# OCI FinOps Helper

A Python-based tool to collect, merge, and enrich Oracle Cloud Infrastructure (OCI) cost and usage data with compute instance metadata.

## Overview

This tool queries the OCI Usage API to retrieve cost and usage information, then enriches the data with compute instance details (shape and resource name) by making additional API calls to the Compute service.

### Key Features

- ✅ **Dual API Calls**: Combines COST and USAGE query types for comprehensive data
- ✅ **Automatic Enrichment**: Fetches compute instance metadata (shape, display name)
- ✅ **Cost-Saving Recommendations**: Fetches actionable recommendations from Cloud Advisor API
- ✅ **Growth Collection**: Analyze tag structure, tag defaults, and cost-tracking tags
- ✅ **Clean Architecture**: Decoupled Python logic and bash wrapper
- ✅ **Virtual Environment**: Isolated Python dependencies
- ✅ **OCI Cloud Shell Compatible**: Works with instance principal authentication
- ✅ **Production Ready**: Comprehensive error handling and logging

## Directory Structure

```
cost_report/
├── collector.sh                         # Entry point - Bash wrapper script
├── src/
│   ├── collector.py                     # Python collector logic (OOP design)
│   └── utils/
│       ├── api_executor.py              # Cost/Usage API caller
│       ├── executor.py                  # Parallel metadata fetcher
│       ├── progress.py                  # Progress spinner utilities
│       ├── recommendations.py           # Cloud Advisor recommendations fetcher
│       └── __init__.py
├── docs/
│   ├── ARCHITECTURE.md                  # System design and data flow
│   ├── QUICK_REFERENCE.md               # Common usage patterns and examples
│   ├── CHANGELOG.md                     # Version history
│   ├── GROWTH_COLLECTION.md             # Tag analysis and growth collection guide
│   ├── RECOMMENDATIONS.md               # Cost-saving recommendations guide
│   └── RECOMMENDATIONS_QUICK_REFERENCE.md # Recommendations quick reference
├── IMPLEMENTATION_SUMMARY.md            # Summary of recent enhancements
├── LICENSE                              # UPL 1.0 License
└── README.md                            # This file
```

## Prerequisites

- **OCI CLI** installed and configured
- **Python 3.6+** with `pip`
- **OCI Authentication** configured (one of):
  - Instance Principal (automatic in OCI Cloud Shell)
  - API Key configuration file (`~/.oci/config`)
- **IAM Permissions**:
  - `USAGE_REPORT_READ` for tenancy
  - `read` access to compute instances

## Installation

No installation required! The script automatically:
- Creates a Python virtual environment
- Installs required dependencies (pandas, requests)
- Manages all setup on first run

## Usage

### Basic Command

```bash
./collector.sh <tenancy_ocid> <home_region> <from_date> <to_date>
```

### Parameters

| Parameter       | Description                           | Format / Example              |
|----------------|---------------------------------------|-------------------------------|
| `tenancy_ocid` | OCI Tenancy OCID                      | `ocid1.tenancy.oc1..aaaaa...` |
| `home_region`  | Home region for usage API             | `us-ashburn-1`                |
| `from_date`    | Start date                            | `2025-11-01` (YYYY-MM-DD)     |
| `to_date`      | End date                              | `2025-11-04` (YYYY-MM-DD)     |

### Example Usage

```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-11-01 \
  2025-11-04
```

### Running in OCI Cloud Shell

Cloud Shell comes with OCI CLI pre-configured with instance principal authentication:

```bash
# Upload or clone the repository
cd cost_report

# Make the script executable (if needed)
chmod +x collector.sh

# Run the collector
./collector.sh <tenancy_ocid> <region> <from_date> <to_date>
```

## How It Works

The collector follows a multi-step process to gather comprehensive cost data:

### Step 1: COST API Call
Queries OCI Usage API with `queryType: COST` to retrieve:
- Service name
- SKU name
- Resource ID
- Compartment path
- Cost amounts and quantities

### Step 2: USAGE API Call
Queries OCI Usage API with `queryType: USAGE` to retrieve:
- Platform type
- Region
- SKU part number
- Additional usage details

### Step 3: Data Merge
Merges both datasets using `resourceId + timeUsageStarted` as composite key.

### Step 4: Instance Discovery
Scans merged data to identify compute instances (resourceId containing `instance.oc1`).

### Step 5: Metadata Enrichment
For each unique compute instance:
- Extracts region from OCID
- Calls `oci compute instance get` API
- Retrieves shape and display name
- Caches metadata for reuse

### Step 6: Recommendations Collection
Fetches cost-saving recommendations from Oracle Cloud Advisor:
- Calls `oci optimizer recommendation-summary list` API
- Generates human-readable actionable report
- Provides specific CLI commands for implementation
- Categorizes by savings potential and priority

### Step 7: Output Generation
Generates multiple output files with enriched data and recommendations.

## Output Files

The script generates the following files in the working directory:

### 1. output_merged.csv
**Complete enriched dataset** with all fields including:
- Cost metrics: `computedAmount`, `computedQuantity`, `attributedCost`
- Service info: `service`, `skuName`, `skuPartNumber`
- Resource details: `resourceId`, `resourceName`, `shape`
- Organization: `compartmentPath`, `compartmentName`, `compartmentId`
- Platform: `platform`, `region`
- Time period: `timeUsageStarted`, `timeUsageEnded`

### 2. output.csv
**Basic merged data** without instance enrichment (faster generation).

### 3. output.json
**Raw API responses** from both COST and USAGE calls (useful for debugging).

### 4. instance_metadata.json
**Cached instance metadata** to avoid redundant API calls in subsequent runs.

### 5. recommendations.out
**Human-readable actionable recommendations** from Oracle Cloud Advisor with:
- Executive summary: Total savings and priority breakdown
- Savings by category: Descriptive names (e.g., "Boot Volumes - Optimize size and performance")
- Detailed explanations: "What This Means" section for each recommendation
- Step-by-step actions: Specific implementation steps
- CLI commands: Exact OCI CLI commands ready to execute
- Estimated savings in USD (or custom currency)

### 6. recommendations.json
**Raw JSON recommendations** for programmatic access and automation.

See `docs/V2.1_NEW_FEATURES.md` for latest features and `docs/RECOMMENDATIONS.md` for detailed information.

## Cost-Saving Recommendations

The collector automatically fetches actionable cost-saving recommendations from Oracle Cloud Advisor (Optimizer API) with detailed explanations and executable CLI commands.

### Quick Start - Get Recommendations Only

Skip cost/usage collection and fetch only recommendations (completes in seconds):

```bash
# Full command with all parameters
./collector.sh <tenancy_ocid> <region> <from_date> <to_date> --only-recommendations

# Example
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-11-01 \
  2025-11-20 \
  --only-recommendations
```

### Custom Currency

Change currency display (default: USD):

```bash
./collector.sh <tenancy_ocid> <region> <from_date> <to_date> \
  --only-recommendations \
  --currency EUR
```

### Stage Control Options

Control which stages to run for faster testing:

```bash
# Skip cost data collection
./collector.sh <params> --skip-cost

# Skip usage data collection
./collector.sh <params> --skip-usage

# Skip metadata enrichment
./collector.sh <params> --skip-enrichment

# Skip recommendations
./collector.sh <params> --skip-recommendations

# Combine multiple flags
./collector.sh <params> --skip-cost --skip-usage --only-recommendations
```

## Growth Collection - Tag Analysis

**NEW in v2.2:** Comprehensive tag analysis for understanding your tagging structure, cost allocation, and growth patterns.

### What It Collects

The growth collection feature analyzes six key aspects of your OCI tagging:

| Data Point | Purpose |
|------------|---------|
| **Tag Namespaces** | Understand tagging structure |
| **Tag Definitions** | Available tags per namespace |
| **Tag Defaults** | Auto-tagging rules |
| **Defined Tags on Resources** | Cost allocation & chargeback |
| **Freeform Tags on Resources** | Custom metadata tracking |
| **Cost-Tracking Tags** | Tag-based cost breakdown |

### Quick Start

#### Option 1: Growth Collection Only
```bash
./collector.sh <tenancy_ocid> <region> <from_date> <to_date> --only-growth
```

**Example:**
```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-11-01 \
  2025-12-01 \
  --only-growth
```

#### Option 2: Full Collection with Growth Data
```bash
./collector.sh <tenancy_ocid> <region> <from_date> <to_date> --growth-collection
```

### Output Files

**growth_collection_tags.json** - Complete JSON with all tag data:
- Tag namespaces and definitions
- Tag defaults (auto-tagging rules)
- Resource tag statistics
- Cost breakdown by tags

**growth_collection_summary.txt** - Human-readable summary report:
- Executive summary of tag usage
- Top cost-driving tag combinations
- Tag compliance statistics
- Compartment-level tag defaults

### Use Cases

- **Cost Allocation:** Identify which tags drive the most cost
- **Chargeback:** Tag-based cost breakdown for departments/projects
- **Compliance:** Ensure resources are properly tagged
- **Governance:** Review and validate auto-tagging rules
- **Trend Analysis:** Track tagging patterns over time

See `docs/GROWTH_COLLECTION.md` for detailed documentation.

### Stage Control Options

Control which stages to run for faster testing:

```bash
# Skip cost data collection
./collector.sh <params> --skip-cost

# Skip usage data collection
./collector.sh <params> --skip-usage

# Skip metadata enrichment
./collector.sh <params> --skip-enrichment

# Skip recommendations
./collector.sh <params> --skip-recommendations

# Combine multiple flags
./collector.sh <params> --skip-cost --skip-usage --only-recommendations
```

### Output Files

**recommendations.out** - Human-readable actionable report with:
- Executive summary with total savings and priority counts
- Savings by category with descriptive names
- Detailed recommendations with:
  - **What This Means**: Explanation of the optimization opportunity
  - **Actions to Take**: Step-by-step implementation guide
  - **CLI Command to Execute**: Exact OCI CLI command to run

**recommendations.json** - Raw JSON data for programmatic access

### Example Output

```
💰 Total Potential Savings: 4,394.98 USD/month
📊 Total Recommendations: 22

SAVINGS BY CATEGORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Boot Volumes - Optimize size and performance settings
   Potential Savings:  1,756.00 USD
   Affected Resources: 700

2. Compute Commitments - Purchase 1-3 year commitments for discounts
   Potential Savings:  1,169.13 USD
   Affected Resources: 3

[1] COST-MANAGEMENT-COMPUTE-HOST-TERMINATED-NAME
────────────────────────────────────────────────────────────────────────────────
Priority:        CRITICAL
Savings:         9.74 USD/month

WHAT THIS MEANS:
  You have 1 compute instance(s) in TERMINATED or STOPPED state that still 
  have associated resources (boot volumes, reserved IPs) incurring costs.

ACTIONS TO TAKE:
  1. List the 1 terminated/stopped instance(s)
  2. Verify these instances are no longer needed
  3. Delete associated boot volumes
  4. Release any reserved public IPs

CLI COMMAND TO EXECUTE:
  oci compute instance list --compartment-id <tenancy-ocid> \
    --lifecycle-state TERMINATED --region us-ashburn-1
```

For detailed guidance on recommendations, see:
- `docs/RECOMMENDATIONS.md` - Complete guide
- `docs/RECOMMENDATIONS_QUICK_REFERENCE.md` - Quick reference with examples
- `docs/V2.1_NEW_FEATURES.md` - Latest v2.1 features

## Performance Notes

### Data Volume
- **Small queries** (1-7 days): ~1-2 minutes
- **Medium queries** (1 month): ~5-10 minutes
- **Large queries** (3+ months): ~30+ minutes

### Recommendations Fetching
- **API call time**: ~2-10 seconds
- **File size**: ~50KB-500KB

### Instance Enrichment
The script makes **one API call per unique compute instance**:
- 100 instances: ~1-2 minutes
- 500 instances: ~5-10 minutes
- 1000+ instances: ~15-30 minutes

**Note**: Terminated instances may fail to fetch metadata (this is expected).

## Troubleshooting

### Authentication Errors

```bash
# Verify OCI CLI authentication
oci iam region list
```

If this fails:
- **Cloud Shell**: Ensure you're in OCI Cloud Shell (instance principal auto-configured)
- **Local/VM**: Check `~/.oci/config` file exists and is properly configured

### API Errors

Common issues:
- **403 Forbidden**: Check IAM permissions for Usage Reports
- **Wrong region**: Ensure home_region matches your tenancy's home region
- **Invalid OCID**: Verify tenancy OCID is correct

### Missing Instance Metadata

This is normal for:
- Terminated instances (no longer accessible via API)
- Instances in regions without API access
- Cross-tenancy resources

### Dependency Issues

```bash
# Recreate virtual environment
rm -rf venv
./collector.sh <parameters>
```

### Large Output Files

For queries spanning many months:
- Split into smaller date ranges
- Process monthly chunks separately
- Merge CSV files manually if needed

## API Limitations

The OCI Usage API has specific constraints:

- ✋ **Max 4 groupBy parameters** per query
- ✋ **Specific valid groupBy keys** only (documented list)
- ✋ **shape and resourceName NOT available** in Usage API groupBy

This is why the tool uses a **dual-call + enrichment approach**:
1. Two separate API calls with different groupBy combinations
2. Merge results on resourceId
3. Enrich with Compute API for instance metadata

### Valid groupBy Keys

The following are valid groupBy parameters for the Usage API:
- `service`, `resourceId`, `compartmentPath`, `compartmentName`, `compartmentId`
- `skuName`, `skuPartNumber`, `unit`
- `platform`, `region`, `logicalAd`
- `tenantId`, `tenantName`
- `tagNamespace`, `tagKey`, `tagValue`

**Not supported**: `shape`, `resourceName` (requires Compute API)

## Advanced Usage

### Analyze Output Data

```bash
# View top 10 most expensive resources
head -1 output_merged.csv && tail -n +2 output_merged.csv | sort -t, -k7 -rn | head -10

# Count resources by service
tail -n +2 output_merged.csv | awk -F, '{print $19}' | sort | uniq -c | sort -rn

# Calculate total cost
tail -n +2 output_merged.csv | awk -F, '{sum+=$7} END {print "Total Cost: $" sum}'
```

### Reuse Cached Metadata

Keep `instance_metadata.json` in the directory to reuse instance metadata across multiple date range queries (saves API calls).

### Process Large Date Ranges

For optimal performance with large queries:

```bash
# Split into monthly chunks
./collector.sh <ocid> <region> 2025-01-01 2025-01-31
./collector.sh <ocid> <region> 2025-02-01 2025-02-28
./collector.sh <ocid> <region> 2025-03-01 2025-03-31

# Then merge CSV files manually
```

## Documentation

- **[README.md](README.md)** - This file: Getting started, usage, troubleshooting
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design, data flow, API integration
- **[docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** - Common usage patterns and examples
- **[docs/CHANGELOG.md](docs/CHANGELOG.md)** - Version history and migration guide

## Examples

### Last 7 Days

```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  $(date -d '7 days ago' +%Y-%m-%d) \
  $(date +%Y-%m-%d)
```

### Current Month

```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  $(date +%Y-%m-01) \
  $(date +%Y-%m-%d)
```

### Specific Date Range

```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-10-01 \
  2025-10-31
```

## License

Copyright (c) 2022 Oracle and/or its affiliates.

Licensed under the **Universal Permissive License (UPL), Version 1.0**.

See [LICENSE](LICENSE) file for details.

## Support

This is a **community tool** and is not officially supported by Oracle.

For issues, questions, or contributions, please use the repository's issue tracker.

## Version History

### v2.0 (November 2025) - Current
- 🎯 Decoupled architecture (Python + Bash)
- 🔄 Automatic virtual environment management
- 💎 Compute instance metadata enrichment
- 📊 Dual API call strategy (COST + USAGE)
- 📝 Comprehensive documentation
- ✨ Improved error handling and progress reporting

### v1.0 (August 2022) - Legacy
- Basic cost data collection
- Single API call approach
- Monolithic script design

---

**Need help?** Check the [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) for common patterns or [ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.
