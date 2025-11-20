# Cost-Saving Recommendations Feature

## Overview

The OCI Cost Report Collector has been enriched with a new feature to automatically fetch cost-saving recommendations from the **Oracle Cloud Advisor API** (Optimizer API). This enhancement allows you to collect potential cost optimization opportunities directly from your Oracle Cloud environment.

## What's New

The collector now performs the following additional operations:

1. **Fetches recommendations** from the Oracle Cloud Advisor API
2. **Categorizes recommendations** by type and status
3. **Calculates estimated monthly savings** when available
4. **Saves all recommendations** to a dedicated output file

## Output File

### Location
```
output/recommendations.out
```

### Format
The recommendations are saved in JSON format with the following structure:

```json
{
  "items": [
    {
      "id": "recommendation-ocid",
      "category": "COMPUTE_OPTIMIZATION",
      "name": "Recommendation Name",
      "description": "Detailed description...",
      "resourceId": "resource-ocid",
      "resourceType": "Instance",
      "lifecycleState": "ACTIVE",
      "estimatedCostSaving": 1234.56,
      "importance": "CRITICAL",
      "recommendedActions": ["Action 1", "Action 2"],
      "...": "additional fields"
    }
  ]
}
```

## Recommendation Categories

The Oracle Cloud Advisor can provide recommendations in these categories:

- **COMPUTE_OPTIMIZATION**: Compute instance sizing and configuration recommendations
- **STORAGE_OPTIMIZATION**: Storage and volume optimization suggestions
- **DATABASE_OPTIMIZATION**: Database configuration and sizing recommendations
- **NETWORKING_OPTIMIZATION**: Network configuration improvements
- **COST_MANAGEMENT**: General cost management recommendations

## Recommendation States

Recommendations have the following lifecycle states:

- **ACTIVE**: New recommendations that haven't been acted upon
- **DISMISSED**: Recommendations that have been dismissed by users
- **IMPLEMENTED**: Recommendations that have been implemented

## API Integration Details

### Endpoint
```
https://optimizer.{region}.oraclecloud.com/20200630/recommendations
```

### Method
The collector uses the OCI CLI command:
```bash
oci optimizer recommendation list \
  --compartment-id <tenancy-ocid> \
  --include-resource-metadata true \
  --sort-order DESC \
  --sort-by importance
```

### Requirements

To fetch recommendations, ensure:

1. **OCI CLI** is installed and authenticated
2. **Cloud Advisor API access** is enabled in your OCI tenancy
3. **Appropriate IAM permissions** are configured
4. Your **home region** is correctly specified

### Required IAM Permissions

Ensure your OCI user/instance principal has these permissions:

```
ALLOW {group|user} to read optimizer-recommendations IN TENANCY
ALLOW {group|user} to read optimizer-resource-actions IN TENANCY
```

## Output Summary

During execution, the collector displays a summary of recommendations:

```
💡 Fetching Cost-Saving Recommendations
======================================================================
Endpoint: https://optimizer.us-ashburn-1.oraclecloud.com/20200630/recommendations
Tenancy: ocid1.tenancy.oc1..aaaaaaaa...

✅ Success: Retrieved 45 recommendations

📊 Recommendations Summary:
  - Active: 38
  - Dismissed: 5
  - Implemented: 2

📈 Recommendations by Category:
  - COMPUTE_OPTIMIZATION: 20
  - STORAGE_OPTIMIZATION: 15
  - DATABASE_OPTIMIZATION: 8
  - NETWORKING_OPTIMIZATION: 2

💰 Estimated Monthly Savings: $5,234.50
```

## Usage

The recommendations are fetched automatically as part of the regular collector workflow:

```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-20
```

No additional parameters are needed. The recommendations file will be generated in the `output/` directory.

## Error Handling

If recommendations cannot be fetched, the collector will:

1. Display a warning message
2. Continue with the rest of the collection process
3. Allow the overall collector to complete successfully

Common reasons for failures:

- **Cloud Advisor API not enabled**: Contact your OCI account administrator
- **Insufficient IAM permissions**: Verify your user/instance principal permissions
- **Region unavailable**: The Cloud Advisor service may not be available in your region
- **Network connectivity**: Verify OCI CLI can reach the API endpoint

## Integration with Other Output Files

The recommendations output complements the existing collector outputs:

| File | Purpose |
|------|---------|
| `output_merged.csv` | Cost and usage data with enrichment |
| `output.csv` | Basic merged cost data |
| `out.json` | Raw API responses from Cost API |
| `instance_metadata.json` | Cached compute instance metadata |
| `recommendations.out` | **NEW** - Cost-saving recommendations |
| `request_*.json` | API request payloads for debugging |

## Processing Recommendations

After the collector completes, you can process the recommendations file:

### Parse and filter by category

```python
import json

with open('output/recommendations.out', 'r') as f:
    data = json.load(f)

# Filter by category
compute_recs = [r for r in data['items'] if r['category'] == 'COMPUTE_OPTIMIZATION']
print(f"Found {len(compute_recs)} compute optimization recommendations")
```

### Calculate total estimated savings

```python
total_savings = sum(
    float(r.get('estimatedCostSaving', 0)) 
    for r in data['items'] 
    if r.get('estimatedCostSaving')
)
print(f"Total estimated monthly savings: ${total_savings:,.2f}")
```

### Export to CSV

```python
import pandas as pd
import json

with open('output/recommendations.out', 'r') as f:
    data = json.load(f)

df = pd.DataFrame(data['items'])
df.to_csv('output/recommendations.csv', index=False)
```

## Architecture

```
collector.sh
    ├── setup_venv()
    ├── check_oci_auth()
    └── run_collector()
        └── collector.py
            ├── Cost API call
            ├── Usage API call
            ├── Merge and enrich
            └── Fetch recommendations
                └── OCIRecommendationsFetcher
                    ├── fetch_recommendations()
                    └── save_recommendations()
```

## Troubleshooting

### No recommendations returned

```
✅ Success: Retrieved 0 recommendations
```

This may indicate:

- Your environment has no optimization opportunities
- Cloud Advisor hasn't analyzed your environment yet
- All recommendations have been dismissed or implemented

**Solution**: Wait 24-48 hours after deploying resources for Cloud Advisor to analyze and generate recommendations.

### API timeout

```
❌ API call timeout after 300 seconds
```

**Solution**: Check your network connectivity and Cloud Advisor API availability. Retry after a few minutes.

### Permission denied

```
❌ Failed to fetch recommendations: ...permission...
```

**Solution**: Verify IAM permissions and OCI CLI authentication are properly configured.

## Performance Impact

- **Recommendation fetching**: ~2-10 seconds depending on API responsiveness
- **No impact on cost/usage data collection**: Fetching recommendations happens after main data collection
- **File size**: Typically 50KB-500KB per file (depends on number and size of recommendations)

## Future Enhancements

Potential improvements for future releases:

- Export recommendations to CSV format
- Automated recommendation tracking and trending
- Cost-benefit analysis integration
- Recommendation action automation
- Dashboard integration
