# Architecture Documentation

## System Overview

The OCI Cost Report Collector is designed with a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      User Invocation                         │
│                    ./collector.sh <args>                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Bash Wrapper (collector.sh)                │
│  • Validates arguments                                       │
│  • Checks OCI CLI authentication                             │
│  • Creates/activates Python virtual environment              │
│  • Installs dependencies (pandas, requests)                  │
│  • Invokes Python collector                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Python Collector (src/collector.py)             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 1: COST API Call                                │   │
│  │ • Query OCI Usage API (queryType: COST)              │   │
│  │ • groupBy: service, skuName, resourceId,             │   │
│  │           compartmentPath                            │   │
│  │ • Returns: Financial data with service details       │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 2: USAGE API Call                               │   │
│  │ • Query OCI Usage API (queryType: USAGE)             │   │
│  │ • groupBy: resourceId, platform, region,             │   │
│  │           skuPartNumber                              │   │
│  │ • Returns: Consumption data with platform details    │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 3: Data Merge                                   │   │
│  │ • Merge key: resourceId + timeUsageStarted           │   │
│  │ • Left join: COST data + USAGE data                  │   │
│  │ • Output: Combined dataset with all fields           │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 4: Extract Compute Instances                    │   │
│  │ • Filter resourceId containing 'instance.oc1'        │   │
│  │ • Extract unique instance OCIDs                      │   │
│  │ • Parse region from OCID structure                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 5: Fetch Instance Metadata                      │   │
│  │ • For each instance:                                 │   │
│  │   - Call: oci compute instance get                   │   │
│  │   - Extract: shape, display-name                     │   │
│  │   - Cache: Store in instance_metadata.json           │   │
│  │ • Handle errors for terminated instances             │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 6: Enrich Dataset                               │   │
│  │ • Apply instance metadata to merged data             │   │
│  │ • Update shape and resourceName fields               │   │
│  │ • Preserve all other fields unchanged                │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Step 7: Generate Outputs                             │   │
│  │ • output_merged.csv: Complete enriched data          │   │
│  │ • output.csv: Basic merged data                      │   │
│  │ • output.json: Raw API responses                     │   │
│  │ • instance_metadata.json: Metadata cache             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Input Flow

```
User Parameters
    │
    ├── tenancy_ocid ────────────┐
    ├── home_region ─────────────┤
    ├── from_date ───────────────┤──→ API Request Bodies
    └── to_date ─────────────────┘
```

### Processing Flow

```
OCI Usage API (COST)          OCI Usage API (USAGE)
        │                              │
        │ JSON Response                │ JSON Response
        ▼                              ▼
    DataFrame 1                    DataFrame 2
        │                              │
        └──────────┬───────────────────┘
                   │
                   ▼
              Pandas Merge
                   │
                   ├──→ output.csv (basic)
                   │
                   ▼
         Extract Instance IDs
                   │
                   ▼
         OCI Compute API (per instance)
                   │
                   ├──→ instance_metadata.json (cache)
                   │
                   ▼
         Enrich DataFrame
                   │
                   └──→ output_merged.csv (enriched)
```

## Component Details

### Bash Wrapper (collector.sh)

**Responsibilities:**
- Environment setup and validation
- Dependency management
- Python virtual environment lifecycle
- Error handling and user feedback

**Key Functions:**
- `check_oci_auth()` - Validates OCI CLI access
- `setup_venv()` - Creates and configures virtual environment
- `run_collector()` - Executes Python script with arguments

### Python Collector (src/collector.py)

**Main Class:** `OCICostCollector`

**Methods:**

1. `__init__(tenancy_ocid, home_region, from_date, to_date)`
   - Initializes collector with user parameters
   - Constructs API endpoint URL

2. `make_api_call(query_type, group_by_fields, call_name)`
   - Builds request body
   - Executes OCI CLI raw-request
   - Parses and validates response
   - Returns API data or None on error

3. `fetch_instance_metadata(instance_ids)`
   - Iterates through instance OCIDs
   - Extracts region from OCID
   - Calls Compute API per instance
   - Returns metadata dictionary

4. `merge_and_enrich(data1, data2)`
   - Converts API responses to DataFrames
   - Merges on composite key
   - Identifies compute instances
   - Enriches with metadata
   - Generates output files

5. `collect()`
   - Orchestrates entire workflow
   - Calls methods in sequence
   - Handles errors and reporting

## API Integration

### OCI Usage API

**Endpoint:**
```
https://usageapi.{region}.oci.oraclecloud.com/20200107/usage
```

**Request Structure:**
```json
{
  "tenantId": "ocid1.tenancy...",
  "timeUsageStarted": "2025-11-01T00:00:00Z",
  "timeUsageEnded": "2025-11-04T00:00:00Z",
  "granularity": "DAILY",
  "queryType": "COST",
  "groupBy": ["service", "skuName", "resourceId", "compartmentPath"],
  "compartmentDepth": 4
}
```

**Response Structure:**
```json
{
  "items": [
    {
      "service": "Compute",
      "skuName": "Standard - X9 - Memory",
      "resourceId": "ocid1.instance.oc1...",
      "compartmentPath": "root/prod/webservers",
      "computedAmount": 123.45,
      "computedQuantity": 720.0,
      "currency": "USD",
      "timeUsageStarted": "2025-11-01T00:00:00.000Z",
      "timeUsageEnded": "2025-11-02T00:00:00.000Z"
    }
  ]
}
```

### OCI Compute API

**Command:**
```bash
oci compute instance get --instance-id <ocid> --region <region>
```

**Response Structure:**
```json
{
  "data": {
    "id": "ocid1.instance.oc1...",
    "display-name": "web-server-01",
    "shape": "VM.Standard.E4.Flex",
    "lifecycle-state": "RUNNING",
    ...
  }
}
```

## Data Schema

### Merged Dataset Fields

| Field | Source | Type | Description |
|-------|--------|------|-------------|
| `service` | COST API | string | OCI service name |
| `skuName` | COST API | string | SKU description |
| `resourceId` | Both | string | Resource OCID |
| `compartmentPath` | COST API | string | Compartment hierarchy |
| `computedAmount` | Both | float | Cost in currency |
| `computedQuantity` | Both | float | Usage quantity |
| `currency` | COST API | string | Currency code |
| `platform` | USAGE API | string | Platform type |
| `region` | USAGE API | string | Region name |
| `skuPartNumber` | USAGE API | string | Oracle part number |
| `shape` | Compute API | string | Instance shape (enriched) |
| `resourceName` | Compute API | string | Display name (enriched) |
| `timeUsageStarted` | Both | datetime | Period start |
| `timeUsageEnded` | Both | datetime | Period end |

## Performance Characteristics

### Time Complexity

- **API Calls**: O(1) for Usage API, O(n) for Compute API where n = unique instances
- **Merge**: O(m log m) where m = total records
- **Enrichment**: O(m) for applying metadata

### Space Complexity

- **Memory**: O(m) for DataFrames
- **Disk**: ~100KB per day of usage data (before enrichment)

### Bottlenecks

1. **Compute API Calls**: Rate-limited, sequential
2. **Network I/O**: API response size for large date ranges
3. **DataFrame Operations**: Memory usage for large datasets

### Optimization Strategies

1. **Caching**: Reuse `instance_metadata.json` for overlapping queries
2. **Chunking**: Split large date ranges into smaller batches
3. **Parallel Processing**: (Future) Parallelize instance metadata fetches

## Error Handling

### Bash Layer
- Authentication failure → Exit with message
- Missing dependencies → Install automatically
- Invalid arguments → Show usage

### Python Layer
- API errors → Log and return None
- Merge failures → Traceback and exit
- Instance fetch errors → Continue with warnings
- Terminated instances → Skip silently

## Security Considerations

- Uses OCI CLI authentication (instance principal or API keys)
- No credentials stored in code
- Temporary request files cleaned up
- Output files contain sensitive tenancy data (protect accordingly)

## Future Enhancements

### Potential Improvements
1. Parallel instance metadata fetching
2. Support for other resource types (buckets, databases)
3. Incremental updates (delta queries)
4. Custom output formats (Excel, Parquet)
5. Built-in data aggregation and reporting
6. Web UI for result visualization

### Architecture Evolution
```
Current: CLI → Bash → Python → Files
Future:  API → Service → Database → Dashboard
```
