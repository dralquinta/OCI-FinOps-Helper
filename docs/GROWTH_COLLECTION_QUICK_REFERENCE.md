# Growth Collection - Quick Reference

## Basic Commands

### Growth Collection Only (Fastest)
```bash
./collector.sh <tenancy> <region> <from_date> <to_date> --only-growth
```

### Full Collection + Growth Data
```bash
./collector.sh <tenancy> <region> <from_date> <to_date> --growth-collection
```

## Example Commands

### Standard 30-Day Tag Analysis
```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-11-01 \
  2025-12-01 \
  --only-growth
```

### Quarterly Tag Analysis (90 Days)
```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-09-01 \
  2025-12-01 \
  --only-growth
```

### Combined: Cost + Usage + Recommendations + Growth
```bash
./collector.sh \
  ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq \
  us-ashburn-1 \
  2025-11-01 \
  2025-12-01 \
  --growth-collection
```

## Output Files

| File | Description |
|------|-------------|
| `growth_collection_tags.json` | Complete JSON data with all tag information |
| `growth_collection_summary.txt` | Human-readable summary report |

## What Gets Collected

| Data Point | What It Shows | Use Case |
|------------|---------------|----------|
| **Tag Namespaces** | Top-level tag containers | Understand tag organization |
| **Tag Definitions** | Individual tags per namespace | See all available tags |
| **Tag Defaults** | Auto-tagging rules | Review governance policies |
| **Resource Tags** | Tags applied to resources | Compliance & coverage analysis |
| **Cost-Tracking Tags** | Cost breakdown by tag | Chargeback & allocation |

## Common Use Cases

### 1. Monthly Tag Compliance Audit
```bash
# Run this monthly to track tagging compliance
./collector.sh <tenancy> <region> $(date -d "1 month ago" +%Y-%m-01) $(date +%Y-%m-%d) --only-growth
```

### 2. Cost Allocation Report
```bash
# Focus on cost-tracking tags for chargeback
./collector.sh <tenancy> <region> 2025-11-01 2025-12-01 --only-growth

# Then check growth_collection_tags.json -> cost_tracking_tags.cost_by_tag
```

### 3. Tag Structure Analysis
```bash
# Review tag namespaces and definitions
./collector.sh <tenancy> <region> 2025-11-01 2025-11-01 --only-growth

# Check growth_collection_tags.json -> tag_namespaces and tag_definitions
```

### 4. Auto-Tagging Rules Audit
```bash
# Review tag defaults across all compartments
./collector.sh <tenancy> <region> 2025-11-01 2025-11-01 --only-growth

# Check growth_collection_summary.txt -> TAG DEFAULTS section
```

## Python API Usage

### Standalone Growth Collection
```python
from src.utils.growth_collector import OCIGrowthCollector

# Default performance settings (10 workers for tags, 20 for compartments)
collector = OCIGrowthCollector(
    tenancy_ocid='ocid1.tenancy.oc1..aaaaa',
    home_region='us-ashburn-1',
    output_dir='output'
)

# Custom performance tuning (increase workers for large tenancies)
collector = OCIGrowthCollector(
    tenancy_ocid='ocid1.tenancy.oc1..aaaaa',
    home_region='us-ashburn-1',
    output_dir='output',
    max_workers_tags=20,           # More parallel workers for tag definitions
    max_workers_compartments=50    # More parallel workers for tag defaults
)

results = collector.collect_all(
    from_date='2025-11-01',
    to_date='2025-12-01'
)
```

### Individual Data Collection
```python
# Collect only tag namespaces
namespaces = collector.collect_tag_namespaces()

# Collect only tag definitions
definitions = collector.collect_tag_definitions()

# Collect only tag defaults
defaults = collector.collect_tag_defaults()

# Collect only resource tags
resource_tags = collector.collect_resource_tags('2025-11-01', '2025-12-01')

# Collect only cost-tracking tags
cost_tags = collector.collect_cost_tracking_tags('2025-11-01', '2025-12-01')
```

## Analyzing Results

### Load JSON Data
```python
import json

with open('output/growth_collection_tags.json') as f:
    data = json.load(f)

# Access different sections
tag_namespaces = data['tag_namespaces']
tag_definitions = data['tag_definitions']
tag_defaults = data['tag_defaults']
resource_tags = data['resource_tags']
cost_tracking = data['cost_tracking_tags']
```

### Top Cost-Driving Tags
```python
cost_by_tag = data['cost_tracking_tags']['cost_by_tag']

# Sort by total cost
sorted_tags = sorted(
    cost_by_tag.items(),
    key=lambda x: x[1]['total_cost'],
    reverse=True
)

# Print top 10
for tag_name, tag_data in sorted_tags[:10]:
    print(f"{tag_name}: ${tag_data['total_cost']:,.2f}")
```

### Tag Coverage Analysis
```python
rt = data['resource_tags']
total_records = rt['total_records']
resources_with_tags = rt['resources_with_tags_count']

coverage_pct = (resources_with_tags / total_records * 100) if total_records > 0 else 0
print(f"Tag coverage: {coverage_pct:.1f}% ({resources_with_tags}/{total_records})")
```

### Export to CSV
```python
import pandas as pd

# Convert cost tracking data to DataFrame
cost_data = []
for tag_name, tag_info in cost_by_tag.items():
    cost_data.append({
        'tag': tag_name,
        'namespace': tag_info['namespace'],
        'key': tag_info['key'],
        'value': tag_info['value'],
        'total_cost': tag_info['total_cost']
    })

df = pd.DataFrame(cost_data)
df.to_csv('tag_costs.csv', index=False)
```

## Performance

| Collection Type | Typical Time | Optimization | Data Volume |
|----------------|--------------|--------------|-------------|
| Tag Namespaces | 2-5 seconds | Single-threaded | KB |
| Tag Definitions | 2-5 seconds | **10 parallel workers** | KB |
| Tag Defaults | 1-3 minutes | **20 parallel workers** | KB |
| Resource Tags | 30-60 seconds | Single API call | MB |
| Cost-Tracking Tags | 30-60 seconds | Single API call | MB |
| **Total** | **2-5 minutes** | **Parallel processing** | **1-10 MB** |

**Performance Improvements in v2.1.1:**
- 🚀 **90% faster** tag defaults collection (parallel processing)
- 🚀 **75% faster** tag definitions collection (parallel processing)
- 🎯 Large tenancies (2000+ compartments): ~13min → ~2-3min

## Required IAM Permissions

```
# Identity permissions for tag data
Allow group FinOpsUsers to inspect tag-namespaces in tenancy
Allow group FinOpsUsers to inspect tag-defaults in tenancy
Allow group FinOpsUsers to read tag-namespaces in tenancy

# Usage API permissions for cost/usage data
Allow group FinOpsUsers to read usage-reports in tenancy

# Compartment listing
Allow group FinOpsUsers to inspect compartments in tenancy
```

## Troubleshooting

### No tag namespaces found
- **Cause:** No tag namespaces defined or insufficient permissions
- **Fix:** Create tag namespaces or verify IAM permissions

### Empty resource_tags data
- **Cause:** Date range too narrow or no tagged resources
- **Fix:** Expand date range to 30-90 days

### Timeout during collection
- **Cause:** Large number of compartments
- **Fix:** Normal behavior, wait for completion

### Permission denied errors
- **Cause:** Missing IAM permissions
- **Fix:** Add required permissions (see above)

## Best Practices

1. **Run Monthly:** Track tagging trends over time
2. **30-90 Day Windows:** Best for cost-tracking analysis
3. **Archive Results:** Keep historical data for compliance
4. **Off-Peak Hours:** Run during low-traffic periods
5. **Compare Periods:** Track month-over-month changes

## Additional Resources

- **Full Documentation:** `docs/GROWTH_COLLECTION.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Main README:** `README.md`

## Version History

- **v2.1** (2025-12-11): Added growth collection feature
- **v2.0** (2025-11): Multi-stage collector
- **v1.0** (2024): Initial release
