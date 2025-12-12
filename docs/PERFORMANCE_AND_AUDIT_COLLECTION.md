# Performance Metrics & Audit Collection

## Overview

As of version 2.2, the Growth Collection feature now includes comprehensive performance metrics, audit events, and event rules collection. This enhancement provides deep visibility into:
- **Resource Performance:** CPU, memory, storage, network, and load balancer metrics
- **User Activity:** Who did what and when via audit events
- **Automation:** Event-driven workflows and automated actions

## Quick Start

### Collect All Data
```bash
./collector.sh <TENANCY_OCID> <REGION> <FROM_DATE> <TO_DATE> --only-growth
```

Example:
```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-12-01 2025-12-12 --only-growth
```

This will collect:
- Tag analysis data (namespaces, definitions, defaults, usage, costs)
- Performance metrics (compute, storage, network, database, load balancer)
- Audit events (resource lifecycle, user actions)
- Event rules (automated actions and workflows)

## Data Points Collected

### Performance Metrics

| Resource Type | Namespace | Metrics Collected | Purpose |
|--------------|-----------|-------------------|---------|
| **Compute Instances** | `oci_computeagent` | CpuUtilization, MemoryUtilization | Identify resource saturation |
| **Block Volumes** | `oci_blockstore` | VolumeReadThroughput, VolumeWriteThroughput | IOPS usage patterns |
| **Virtual Cloud Network** | `oci_vcn` | VnicToNetworkBytes, VnicFromNetworkBytes | Bandwidth usage |
| **Databases** | `oci_database` | CpuUtilization, StorageUtilization | DB resource usage |
| **Load Balancers** | `oci_lbaas` | ActiveConnections, ConnectionCount | Load balancer load |

### Audit Events

Collects audit log events from all compartments to track:
- Resource creation, modification, and deletion
- User actions and identity information
- Event types and resource types
- Lifecycle patterns and growth trends

### Event Rules

Collects event rules configuration from all compartments:
- Active and inactive rules
- Action types (notifications, functions, streaming, etc.)
- Event patterns and conditions
- Automated workflow documentation

## Use Cases

### 1. Performance Optimization & Rightsizing

**Goal:** Identify underutilized or oversaturated resources

**Steps:**
1. Run growth collection for 30-day period
2. Review `performance_metrics` in output JSON
3. Look for:
   - High CPU/memory utilization → potential bottlenecks
   - Low utilization → rightsizing opportunities
   - Storage throughput patterns → storage tier optimization

**Example Analysis:**
```python
import json

with open('output/growth_collection_tags.json') as f:
    data = json.load(f)

metrics = data['performance_metrics']['metrics_by_namespace']

# Check compute metrics
compute_metrics = metrics['oci_computeagent']['metrics']
cpu_data = compute_metrics['CpuUtilization']['samples']

# Identify high utilization instances
for sample in cpu_data:
    if sample.get('aggregatedDatapoints', [{}])[0].get('value', 0) > 80:
        print(f"High CPU: {sample}")
```

### 2. Security & Compliance Auditing

**Goal:** Track who created/modified resources for compliance

**Steps:**
1. Run growth collection for audit period
2. Review `audit_events` in output JSON
3. Analyze:
   - Top event types (CreateInstance, UpdateBucket, etc.)
   - User activity patterns
   - Unusual or unauthorized actions

**Example Analysis:**
```python
# Review audit events
audit_data = data['audit_events']

print(f"Total Events: {audit_data['total_events']}")
print(f"Unique Users: {audit_data['unique_users']}")

# Top event types
for event_type, count in list(audit_data['event_types'].items())[:10]:
    print(f"{event_type}: {count}")

# Filter for specific resource creation
for event in audit_data['sample_events']:
    if 'Create' in event.get('data', {}).get('eventName', ''):
        user = event.get('data', {}).get('identity', {}).get('principalName', 'Unknown')
        resource = event.get('data', {}).get('resourceName', 'Unknown')
        print(f"{user} created {resource}")
```

### 3. Capacity Planning

**Goal:** Predict future resource needs based on trends

**Steps:**
1. Run growth collection monthly
2. Compare metrics over time
3. Identify growth patterns:
   - Increasing CPU/memory usage trends
   - Storage growth rates
   - Network bandwidth increases

### 4. Automation Documentation

**Goal:** Document existing event-driven automation

**Steps:**
1. Run growth collection (event rules don't require date range)
2. Review `event_rules` in output JSON
3. Generate documentation:
   - Active automation workflows
   - Event patterns and actions
   - Compartments with automation

**Example:**
```python
# Document event rules
rules_data = data['event_rules']

print(f"Total Rules: {rules_data['total_rules']}")
print(f"Enabled: {rules_data['enabled_rules']}")
print(f"Disabled: {rules_data['disabled_rules']}")

# Action types breakdown
for action_type, count in rules_data['action_types'].items():
    print(f"{action_type}: {count} rules")

# List all rules
for rule in rules_data['rules']:
    if rule.get('lifecycle-state') == 'ACTIVE':
        print(f"Active Rule: {rule.get('display-name', 'N/A')}")
```

### 5. Cost-Performance Correlation

**Goal:** Correlate high costs with performance patterns

**Steps:**
1. Run growth collection with cost and performance data
2. Cross-reference:
   - High-cost resources (from `cost_tracking_tags`)
   - Performance metrics (from `performance_metrics`)
3. Identify:
   - Expensive but underutilized resources
   - Performance bottlenecks causing redundancy

## Output Structure

### Performance Metrics
```json
{
  "performance_metrics": {
    "collection_period": {
      "from_date": "2025-12-01",
      "to_date": "2025-12-12"
    },
    "metrics_by_namespace": {
      "oci_computeagent": {
        "display_name": "Compute Instances",
        "metrics": {
          "CpuUtilization": {
            "data_points": 720,
            "samples": [...]
          },
          "MemoryUtilization": {
            "data_points": 720,
            "samples": [...]
          }
        }
      }
    }
  }
}
```

### Audit Events
```json
{
  "audit_events": {
    "collection_period": {
      "from_date": "2025-12-01",
      "to_date": "2025-12-12"
    },
    "total_events": 15234,
    "compartments_with_events": 12,
    "unique_users": 25,
    "event_types": {
      "com.oraclecloud.computeapi.launchinstance": 45,
      "com.oraclecloud.objectstorage.createbucket": 23,
      ...
    },
    "resource_types": {
      "instance": 45,
      "bucket": 23,
      ...
    },
    "sample_events": [...]
  }
}
```

### Event Rules
```json
{
  "event_rules": {
    "total_rules": 42,
    "enabled_rules": 38,
    "disabled_rules": 4,
    "compartments_with_rules": 8,
    "action_types": {
      "ONS": 25,
      "FAAS": 10,
      "OSS": 7
    },
    "rules": [...]
  }
}
```

## Summary Report

The text summary (`growth_collection_summary.txt`) now includes:

```
======================================================================
PERFORMANCE METRICS
----------------------------------------------------------------------
Collection Period: 2025-12-01 to 2025-12-12

Compute Instances:
  - CpuUtilization: 720 data points
  - MemoryUtilization: 720 data points

Block Volumes:
  - VolumeReadThroughput: 720 data points
  - VolumeWriteThroughput: 720 data points

...

======================================================================
AUDIT EVENTS
----------------------------------------------------------------------
Collection Period: 2025-12-01 to 2025-12-12
Total Events: 15234
Unique Users: 25
Compartments with Events: 12

Top 10 Event Types:
  1. com.oraclecloud.computeapi.launchinstance: 45
  2. com.oraclecloud.objectstorage.createbucket: 23
  ...

Top 10 Resource Types:
  1. instance: 45
  2. bucket: 23
  ...

======================================================================
EVENT RULES
----------------------------------------------------------------------
Total Rules: 42
Enabled Rules: 38
Disabled Rules: 4
Compartments with Rules: 8

Action Types:
  - ONS: 25
  - FAAS: 10
  - OSS: 7
```

## Performance Considerations

### Collection Time
- **Performance Metrics:** 2-5 minutes (depends on resource count and date range)
- **Audit Events:** 2-5 minutes (parallel processing across all compartments)
- **Event Rules:** 1-2 minutes (parallel processing across all compartments)

### Optimization
- Parallel processing: 30 workers for compartment-based collections
- Date range: Shorter ranges = faster collection
- Caching: Results stored in JSON for repeated analysis

### API Limits
All collections respect OCI API rate limits. For very large tenancies (>5000 compartments), expect:
- Occasional throttling warnings
- Automatic retry logic
- Total collection time: 10-20 minutes

## Required IAM Permissions

Add these to your existing FinOps policies:

```
# Monitoring/Metrics permissions
Allow group FinOpsUsers to read metrics in tenancy

# Audit permissions
Allow group FinOpsUsers to read audit-events in tenancy

# Events permissions
Allow group FinOpsUsers to read cloudevents-rules in tenancy
Allow group FinOpsUsers to inspect cloudevents-rules in tenancy
```

## Troubleshooting

### No Performance Data
**Problem:** `performance_metrics` shows 0 data points

**Solutions:**
- Verify monitoring is enabled for resources
- Check date range (must have active resources during period)
- Ensure IAM permissions for metrics reading

### Missing Audit Events
**Problem:** `audit_events` shows 0 total events

**Solutions:**
- Verify audit retention period (OCI retains 365 days)
- Check date range falls within retention period
- Ensure IAM permissions for audit-events reading

### Empty Event Rules
**Problem:** `event_rules` shows 0 total rules

**Solutions:**
- Verify event rules are configured in your tenancy
- Check IAM permissions for cloudevents-rules
- Normal if no event-driven automation is configured

## Best Practices

1. **Monthly Collection:** Run monthly to track trends over time
2. **Date Ranges:** Use 30-90 day windows for meaningful analysis
3. **Archive Results:** Keep historical JSON files for trend analysis
4. **Cross-Reference:** Combine with cost data for optimization insights
5. **Alert Thresholds:** Define performance thresholds for proactive monitoring

## Integration Examples

### Export to CSV
```python
import json
import pandas as pd

with open('output/growth_collection_tags.json') as f:
    data = json.load(f)

# Export audit events to CSV
audit_events = []
for event in data['audit_events']['sample_events']:
    audit_events.append({
        'timestamp': event.get('eventTime'),
        'user': event.get('data', {}).get('identity', {}).get('principalName'),
        'event_type': event.get('data', {}).get('eventName'),
        'resource': event.get('data', {}).get('resourceName')
    })

df = pd.DataFrame(audit_events)
df.to_csv('audit_events.csv', index=False)
```

### Visualization
```python
import matplotlib.pyplot as plt

# Plot CPU utilization trend
cpu_samples = data['performance_metrics']['metrics_by_namespace']['oci_computeagent']['metrics']['CpuUtilization']['samples']

timestamps = [s.get('timestamp') for s in cpu_samples]
values = [s.get('aggregatedDatapoints', [{}])[0].get('value', 0) for s in cpu_samples]

plt.figure(figsize=(12, 6))
plt.plot(timestamps, values)
plt.title('CPU Utilization Trend')
plt.xlabel('Time')
plt.ylabel('CPU %')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('cpu_trend.png')
```

## Related Documentation

- [GROWTH_COLLECTION.md](GROWTH_COLLECTION.md) - Main growth collection documentation
- [RECOMMENDATIONS.md](RECOMMENDATIONS.md) - Cost optimization recommendations
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick reference guide

---

**Version:** 2.2  
**Last Updated:** December 12, 2025  
**Maintainer:** OCI FinOps Team
