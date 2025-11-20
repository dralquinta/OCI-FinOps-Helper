# Quick Reference: Cost-Saving Recommendations

## TL;DR

The collector now automatically fetches cost-saving recommendations from Oracle Cloud Advisor and saves them to `output/recommendations.out`.

## Quick Start

```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-20
```

The recommendations file will be automatically generated in the `output/` directory.

## Output File

- **Location**: `output/recommendations.out`
- **Format**: JSON
- **Size**: Typically 50KB-500KB

## Common Tasks

### View all recommendations
```bash
cat output/recommendations.out | python3 -m json.tool | less
```

### Count recommendations
```bash
python3 -c "import json; print(len(json.load(open('output/recommendations.out'))['items']))"
```

### Export to CSV
```bash
python3 -c "
import json, pandas as pd
data = json.load(open('output/recommendations.out'))
df = pd.DataFrame(data['items'])
df.to_csv('output/recommendations.csv', index=False)
print('Saved to recommendations.csv')
"
```

### View recommendations by category
```bash
python3 -c "
import json
data = json.load(open('output/recommendations.out'))
categories = {}
for item in data['items']:
    cat = item.get('category', 'UNKNOWN')
    categories[cat] = categories.get(cat, 0) + 1
for cat, count in sorted(categories.items()):
    print(f'{cat}: {count}')
"
```

### Calculate estimated savings
```bash
python3 -c "
import json
data = json.load(open('output/recommendations.out'))
total = sum(float(r.get('estimatedCostSaving', 0)) for r in data['items'] if r.get('estimatedCostSaving'))
print(f'Estimated Monthly Savings: \${total:,.2f}')
"
```

### View only active recommendations
```bash
python3 -c "
import json
data = json.load(open('output/recommendations.out'))
active = [r for r in data['items'] if r.get('lifecycleState') == 'ACTIVE']
print(f'Active Recommendations: {len(active)}')
for r in active[:5]:
    print(f\"  - {r.get('category')}: {r.get('name')}\")
"
```

### View high-impact recommendations
```bash
python3 -c "
import json
data = json.load(open('output/recommendations.out'))
critical = [r for r in data['items'] if r.get('importance') == 'CRITICAL']
print(f'Critical Recommendations: {len(critical)}')
for r in critical[:5]:
    savings = r.get('estimatedCostSaving', 0)
    print(f\"  - {r.get('category')}: \${savings:,.2f} potential savings\")
"
```

## Recommendation States

| State | Meaning |
|-------|---------|
| ACTIVE | New, not yet implemented |
| DISMISSED | User chose not to implement |
| IMPLEMENTED | Already implemented |

## Recommendation Categories

| Category | Purpose |
|----------|---------|
| COMPUTE_OPTIMIZATION | VM sizing and configuration |
| STORAGE_OPTIMIZATION | Storage and volume improvements |
| DATABASE_OPTIMIZATION | Database settings and sizing |
| NETWORKING_OPTIMIZATION | Network configuration |
| COST_MANAGEMENT | General cost improvements |

## Troubleshooting

### No recommendations found
- Normal for new environments
- Cloud Advisor needs 24-48 hours to analyze
- Check that Cloud Advisor is enabled

### File not created
- Verify OCI CLI authentication: `oci auth` 
- Check IAM permissions
- Verify Cloud Advisor API is available in your region

### Recommendations look incomplete
- May include partial data during first run
- Try running again in 24 hours
- Larger tenancies take longer to analyze

## IAM Permissions Needed

```
ALLOW {group|user} to read optimizer-recommendations IN TENANCY
ALLOW {group|user} to read optimizer-resource-actions IN TENANCY
```

## Files Generated

| File | Contains |
|------|----------|
| recommendations.out | All recommendations (JSON) |
| output_merged.csv | Cost data (CSV) |
| output.csv | Basic cost data (CSV) |
| out.json | Raw API responses (JSON) |
| instance_metadata.json | VM details (JSON) |

## Performance

- Collection Time: +2-10 seconds for recommendations
- File Size: 50KB-500KB typically
- API Calls: 1 additional call to Cloud Advisor

## Documentation

For detailed information, see: `docs/RECOMMENDATIONS.md`

For implementation details, see: `IMPLEMENTATION_SUMMARY.md`

## Support

If issues occur:

1. Check `output/debug_recommendations_response.json` for API response details
2. Verify OCI CLI is working: `oci optimizer recommendation list --compartment-id <TENANCY_OCID>`
3. Check IAM permissions
4. Review OCI Cloud Advisor documentation: https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm
