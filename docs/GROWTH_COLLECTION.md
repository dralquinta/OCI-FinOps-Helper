# Growth Collection - Tag Analysis Feature

## Overview

The Growth Collection feature provides comprehensive tag analysis for OCI (Oracle Cloud Infrastructure) tenancies. It collects and analyzes tag-related data to help you understand your tagging structure, cost allocation, and growth patterns.

## Data Points Collected

The growth collection gathers comprehensive data about your OCI tenancy:

### Tag Analysis Data Points

| Data Point | OCI API | Method/Endpoint | Purpose |
|------------|---------|-----------------|---------|
| **Tag Namespaces** | `oci.identity.IdentityClient` | `list_tag_namespaces(compartment_id)` | Understand tagging structure |
| **Tag Definitions** | `oci.identity.IdentityClient` | `list_tags(tag_namespace_id)` | Available tags per namespace |
| **Defined Tags on Resources** | Each resource API | `list_* methods return defined_tags` | Cost allocation & chargeback |
| **Freeform Tags on Resources** | Each resource API | `list_* methods return freeform_tags` | Custom metadata tracking |
| **Tag Defaults** | `oci.identity.IdentityClient` | `list_tag_defaults(compartment_id)` | Auto-tagging rules |
| **Cost-Tracking Tags** | `oci.usage_api.UsageapiClient` | Query with `tagNamespace`, `tagKey`, `tagValue` in `groupBy` | Tag-based cost breakdown |

### Performance Metrics Data Points

| Data Point | OCI API | Method/Endpoint | Purpose |
|------------|---------|-----------------|---------|
| **Compute Metrics** | `oci.monitoring.MonitoringClient` | `summarize_metrics_data()` with `CpuUtilization`, `MemoryUtilization` | Resource saturation analysis |
| **Storage Metrics** | `oci.monitoring.MonitoringClient` | `summarize_metrics_data()` with `VolumeReadThroughput`, `VolumeWriteThroughput` | IOPS usage patterns |
| **Network Metrics** | `oci.monitoring.MonitoringClient` | `summarize_metrics_data()` with `NetworksBytesIn`, `NetworksBytesOut` | Bandwidth usage |
| **Database Metrics** | `oci.monitoring.MonitoringClient` | `summarize_metrics_data()` with `CpuUtilization`, `StorageUtilization` | DB resource usage |
| **Load Balancer Metrics** | `oci.monitoring.MonitoringClient` | `summarize_metrics_data()` with `ConnectionsCount` | Load balancer load |

### Audit and Event Data Points

| Data Point | OCI API | Method/Endpoint | Purpose |
|------------|---------|-----------------|---------|
| **Audit Events** | `oci.audit.AuditClient` | `list_events(compartment_id, start_time, end_time)` | Resource lifecycle patterns, identify who did what |
| **Event Rules** | `oci.events.EventsClient` | `list_rules(compartment_id)` | Automated actions and event-driven workflows |

## Usage

### Command Line Options

#### Option 1: Growth Collection Only
Collects only tag-related data, skipping cost/usage data collection:

```bash
./collector.sh <TENANCY_OCID> <REGION> <FROM_DATE> <TO_DATE> --only-growth
```

**Example:**
```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-12-01 --only-growth
```

#### Option 2: Full Collection with Growth Data
Runs standard cost/usage collection AND includes growth data:

```bash
./collector.sh <TENANCY_OCID> <REGION> <FROM_DATE> <TO_DATE> --growth-collection
```

**Example:**
```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-12-01 --growth-collection
```

### Direct Python Usage

You can also use the collector directly from Python:

```python
from src.collector import OCICostCollector

# Option 1: Growth collection only
collector = OCICostCollector(
    tenancy_ocid='ocid1.tenancy.oc1..aaaaa',
    home_region='us-ashburn-1',
    from_date='2025-11-01',
    to_date='2025-12-01'
)

collector.collect(
    skip_cost=True,
    skip_usage=True,
    skip_enrichment=True,
    skip_recommendations=True,
    growth_collection=True
)

# Option 2: Include with normal collection
collector.collect(
    growth_collection=True
)
```

Or use the growth collector directly:

```python
from src.utils.growth_collector import OCIGrowthCollector

# Default settings (optimized for most tenancies)
growth_collector = OCIGrowthCollector(
    tenancy_ocid='ocid1.tenancy.oc1..aaaaa',
    home_region='us-ashburn-1',
    output_dir='output'
)

# Custom performance tuning for large tenancies
growth_collector = OCIGrowthCollector(
    tenancy_ocid='ocid1.tenancy.oc1..aaaaa',
    home_region='us-ashburn-1',
    output_dir='output',
    max_workers_tags=20,           # Parallel workers for tag definitions (default: 10)
    max_workers_compartments=50    # Parallel workers for tag defaults (default: 20)
)

results = growth_collector.collect_all(
    from_date='2025-11-01',
    to_date='2025-12-01'
)
```

## Output Files

Growth collection generates two main output files:

### 1. `growth_collection_tags.json`
Complete JSON file containing all collected data:

```json
{
  "collection_timestamp": "2025-12-11T10:30:00.000000",
  "tenancy_ocid": "ocid1.tenancy.oc1..aaaaa",
  "home_region": "us-ashburn-1",
  "compartments": ["ocid1.compartment...", ...],
  "tag_namespaces": [...],
  "tag_definitions": {...},
  "tag_defaults": [...],
  "resource_tags": {...},
  "cost_tracking_tags": {...},
  "performance_metrics": {
    "collection_period": {
      "from_date": "2025-11-01",
      "to_date": "2025-12-01"
    },
    "metrics_by_namespace": {
      "oci_computeagent": {
        "display_name": "Compute Instances",
        "metrics": {
          "CpuUtilization": {"data_points": 720, "samples": [...]},
          "MemoryUtilization": {"data_points": 720, "samples": [...]}
        }
      },
      "oci_blockstore": {...},
      "oci_vcn": {...},
      "oci_database": {...},
      "oci_lbaas": {...}
    }
  },
  "audit_events": {
    "collection_period": {...},
    "total_events": 15234,
    "compartments_with_events": 12,
    "unique_users": 25,
    "event_types": {...},
    "resource_types": {...},
    "sample_events": [...]
  },
  "event_rules": {
    "total_rules": 42,
    "enabled_rules": 38,
    "disabled_rules": 4,
    "compartments_with_rules": 8,
    "action_types": {...},
    "rules": [...]
  }
}
```

### 2. `growth_collection_summary.txt`
Human-readable summary report with key statistics including:
- Compartment summary
- Tag namespaces and definitions
- Tag defaults (auto-tagging rules)
- Resource tags statistics
- Cost-tracking tags analysis
- **Performance metrics by resource type**
- **Audit events summary with top event types**
- **Event rules configuration**

```
======================================================================
OCI Growth Collection - Tag Analysis Summary
======================================================================

Collection Timestamp: 2025-12-11T10:30:00.000000
Tenancy OCID: ocid1.tenancy.oc1..aaaaa
Home Region: us-ashburn-1

----------------------------------------------------------------------
COMPARTMENTS
----------------------------------------------------------------------
Total Compartments: 15

----------------------------------------------------------------------
TAG NAMESPACES
----------------------------------------------------------------------
Total Tag Namespaces: 3
  - Oracle-Tags: Oracle Default Tags
  - CostCenter: Cost allocation tags
  - Environment: Environment classification tags

----------------------------------------------------------------------
TAG DEFINITIONS
----------------------------------------------------------------------
Total Tag Definitions: 12
  Namespace 'Oracle-Tags': 5 tags
    - CreatedBy
    - CreatedOn
    ...

----------------------------------------------------------------------
TAG DEFAULTS (Auto-tagging Rules)
----------------------------------------------------------------------
Total Tag Defaults: 8
  - CostCenter.Department = Engineering
  - Environment.Type = Production
  ...

----------------------------------------------------------------------
RESOURCE TAGS
----------------------------------------------------------------------
Total Records: 1,234
Unique Tag Namespaces: 3
Unique Tag Keys: 12
Resources with Tags: 567

----------------------------------------------------------------------
COST-TRACKING TAGS
----------------------------------------------------------------------
Total Cost Tracked: $45,678.90
Unique Tag Combinations: 25

Top 10 Cost-Driving Tags:
  1. CostCenter.Department=Engineering: $18,234.56
  2. Environment.Type=Production: $15,678.90
  ...
```

## Data Collection Details

### 1. Tag Namespaces
- **What:** Top-level containers for organizing tags
- **API Call:** `oci iam tag-namespace list --compartment-id <tenancy_ocid>`
- **Use Case:** Understand the organizational structure of your tagging system

### 2. Tag Definitions
- **What:** Individual tags within each namespace
- **API Call:** `oci iam tag list --tag-namespace-id <namespace_id>`
- **Use Case:** See all available tags that can be applied to resources
- **Multi-threaded:** Processes all namespaces in parallel for faster collection

### 3. Tag Defaults
- **What:** Auto-tagging rules that automatically apply tags to new resources
- **API Call:** `oci iam tag-default list --compartment-id <compartment_id>`
- **Use Case:** Understand your automated tagging governance
- **Coverage:** Scans all compartments in the tenancy

### 4. Resource Tags
- **What:** Tags actually applied to resources
- **API Call:** Usage API with `groupBy: ["resourceId", "tagNamespace", "tagKey", "tagValue"]`
- **Use Case:** 
  - Cost allocation and chargeback
  - Compliance tracking
  - Resource organization analysis
- **Output:** Statistics on tag usage across resources

### 5. Cost-Tracking Tags
- **What:** Tags with associated cost data
- **API Call:** Usage API (COST query) with `groupBy: ["tagNamespace", "tagKey", "tagValue", "service"]`
- **Use Case:**
  - Identify which tags drive the most cost
  - Tag-based cost allocation
  - Chargeback reporting
- **Output:** Cost breakdown by tag combinations

### 6. Performance Metrics
- **What:** Performance and utilization metrics from OCI Monitoring service
- **API Call:** `oci.monitoring.MonitoringClient.summarize_metrics_data()`
- **Metrics Collected:**
  - **Compute:** CpuUtilization, MemoryUtilization
  - **Storage:** VolumeReadThroughput, VolumeWriteThroughput
  - **Network:** NetworksBytesIn, NetworksBytesOut
  - **Database:** CpuUtilization, StorageUtilization
  - **Load Balancer:** ConnectionsCount
- **Use Case:**
  - Identify resource saturation and bottlenecks
  - Capacity planning and rightsizing
  - Performance optimization opportunities
  - Correlate performance with cost trends
- **Output:** Time-series metrics data for trend analysis

### 7. Audit Events
- **What:** Audit log events tracking resource lifecycle and user actions
- **API Call:** `oci audit event list --compartment-id <compartment_id>`
- **Use Case:**
  - Track who created/modified/deleted resources
  - Identify resource lifecycle patterns
  - Compliance and security auditing
  - Understand growth patterns by user/team
- **Coverage:** Scans all compartments in the tenancy
- **Output:** Event summaries with top event types and users
- **Multi-threaded:** Processes all compartments in parallel

### 8. Event Rules
- **What:** Configured event rules for automated actions
- **API Call:** `oci events rule list --compartment-id <compartment_id>`
- **Use Case:**
  - Understand automated workflows and actions
  - Document event-driven architecture
  - Identify automation opportunities
  - Compliance validation for automated responses
- **Coverage:** Scans all compartments in the tenancy
- **Output:** Rules summary with action types and states
- **Multi-threaded:** Processes all compartments in parallel

## Prerequisites

### Required Permissions

The user/instance principal running the collector must have the following IAM policies:

```
# Identity permissions for tag data
Allow group FinOpsUsers to inspect tag-namespaces in tenancy
Allow group FinOpsUsers to inspect tag-defaults in tenancy
Allow group FinOpsUsers to read tag-namespaces in tenancy

# Usage API permissions for cost/usage data
Allow group FinOpsUsers to read usage-reports in tenancy

# Compartment listing
Allow group FinOpsUsers to inspect compartments in tenancy

# Monitoring/Metrics permissions for performance data
Allow group FinOpsUsers to read metrics in tenancy

# Audit permissions for audit events
Allow group FinOpsUsers to read audit-events in tenancy

# Events permissions for event rules
Allow group FinOpsUsers to read cloudevents-rules in tenancy
Allow group FinOpsUsers to inspect cloudevents-rules in tenancy
```

### OCI CLI Configuration

Ensure OCI CLI is properly configured:
```bash
oci iam tenancy get --tenancy-id <your-tenancy-ocid>
```

## Performance Characteristics

### Collection Speed
- **Tag Namespaces:** ~2-5 seconds
- **Tag Definitions:** ~2-5 seconds (parallel processing with 10 workers)
- **Tag Defaults:** ~1-3 minutes (parallel processing with 20 workers scanning all compartments)
- **Resource Tags:** ~30-60 seconds (depends on data volume)
- **Cost-Tracking Tags:** ~30-60 seconds (depends on data volume)
- **Performance Metrics:** ~2-5 minutes (depends on number of resources and date range)
- **Audit Events:** ~2-5 minutes (parallel processing with 30 workers scanning all compartments)
- **Event Rules:** ~1-2 minutes (parallel processing with 30 workers scanning all compartments)

**Total estimated time:** 5-15 minutes for a typical tenancy (dramatically improved with parallel processing)

**Performance Improvements (v2.1.1):**
- Tag definitions: ~75% faster with parallel processing (10 concurrent workers)
- Tag defaults: ~90% faster with parallel processing (20 concurrent workers)
- Audit events: Parallel processing across all compartments (30 concurrent workers)
- Event rules: Parallel processing across all compartments (30 concurrent workers)
- Large tenancies (2000+ compartments): Reduced from ~13 minutes to ~5-8 minutes

### Resource Usage
- Memory: ~100-500 MB
- Network: API calls are rate-limited by OCI
- Disk: Output files typically 1-10 MB
- CPU: Moderate usage during parallel processing (10-20 concurrent threads)

## Use Cases

### 1. Cost Allocation & Chargeback
Identify which departments/projects are driving cloud costs using cost-tracking tags:
```bash
# Run growth collection
./collector.sh <tenancy> <region> 2025-11-01 2025-12-01 --only-growth

# Analyze growth_collection_tags.json
# Look at cost_tracking_tags.cost_by_tag
```

### 2. Tagging Compliance Audit
Check if resources are properly tagged according to your governance policies:
```bash
# Identify untagged resources
# Compare resource_tags.resources_with_tags_count 
# against total resource count
```

### 3. Tag Structure Analysis
Understand your tagging taxonomy:
```bash
# Review tag_namespaces and tag_definitions
# Identify unused or redundant tags
# Plan tag consolidation
```

### 4. Auto-Tagging Governance
Review and validate your tag default rules:
```bash
# Check tag_defaults for each compartment
# Ensure auto-tagging aligns with policies
```

### 5. Performance Analysis & Optimization
Identify resource saturation and optimization opportunities:
```bash
# Run growth collection with date range
./collector.sh <tenancy> <region> 2025-11-01 2025-12-01 --only-growth

# Analyze performance_metrics in growth_collection_tags.json
# Look for high CPU/memory utilization
# Identify underutilized resources for rightsizing
```

### 6. Audit & Compliance Tracking
Track resource lifecycle and user activity patterns:
```bash
# Review audit_events for compliance
# Identify who created/modified resources
# Track unusual activity patterns
# Generate accountability reports
```

### 7. Automation & Event-Driven Architecture
Understand your automated workflows:
```bash
# Review event_rules across compartments
# Document existing automation
# Identify gaps in event-driven responses
# Plan new automation opportunities
```

## Integration with Other Tools

### Export to CSV for Analysis
```python
import json
import pandas as pd

# Load the JSON data
with open('output/growth_collection_tags.json') as f:
    data = json.load(f)

# Convert cost tracking data to DataFrame
cost_data = data['cost_tracking_tags']['cost_by_tag']
df = pd.DataFrame([
    {
        'tag': tag_name,
        'namespace': info['namespace'],
        'key': info['key'],
        'value': info['value'],
        'total_cost': info['total_cost']
    }
    for tag_name, info in cost_data.items()
])

df.to_csv('tag_costs.csv', index=False)
```

### Visualization with Jupyter
See the example notebook in `jupe-note/growth_analysis.ipynb` (to be created).

## Troubleshooting

### Issue: "No tag namespaces found"
- **Cause:** No tag namespaces defined in tenancy
- **Solution:** Create tag namespaces in OCI Console or verify IAM permissions

### Issue: "Failed to fetch cost-tracking tags"
- **Cause:** Insufficient Usage API permissions
- **Solution:** Add `read usage-reports` permission to your user/group

### Issue: "Timeout during tag defaults collection"
- **Cause:** Large number of compartments
- **Solution:** This is normal; the collector will continue processing

### Issue: "Empty resource_tags data"
- **Cause:** Date range too narrow or no tagged resources
- **Solution:** Expand date range or verify resources have tags

## Best Practices

1. **Run Monthly:** Schedule growth collection monthly to track tagging trends
2. **Compare Over Time:** Keep historical JSON files to analyze tagging evolution
3. **Date Range:** Use 30-90 day windows for meaningful cost-tracking data
4. **Off-Peak Hours:** Run during off-peak hours for large tenancies
5. **Archive Results:** Store results for compliance and audit trails

## Limitations

1. **API Rate Limits:** Subject to OCI API throttling for large tenancies
2. **Historical Data:** Cost/usage data limited to available Usage API history
3. **Resource Coverage:** Resource tags collected via Usage API (active resources only)
4. **Deleted Resources:** Deleted resources not included in resource tag analysis

## Future Enhancements

Planned features:
- [ ] Tag trend analysis over time
- [ ] Tag compliance scoring
- [ ] Automated tag recommendations
- [ ] Integration with OCI Tagging Service for bulk operations
- [ ] Export to Excel with charts

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the logs in the output directory
3. Open an issue in the repository
4. Contact the FinOps team

## Version History

- **v2.2** (2025-12-12): Enhanced growth collection with performance metrics, audit events, and event rules
- **v2.1** (2025-12-11): Added growth collection feature with tag analysis
- **v2.0** (2025-11): Initial multi-stage collector
- **v1.0** (2024): Basic cost collection

---

**Last Updated:** December 12, 2025  
**Maintainer:** OCI FinOps Team
