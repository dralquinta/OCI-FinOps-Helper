# Changelog

## Version 2.1 (December 2025)

### New Feature: Growth Collection - Tag Analysis

#### Overview
Added comprehensive tag analysis capabilities to help understand tagging structure, cost allocation, and growth patterns across your OCI tenancy.

#### What's New
- **`--growth-collection` flag**: Collect tag-related data alongside regular cost/usage collection
- **`--only-growth` flag**: Run only tag analysis (skip cost/usage data)
- **New utility module**: `src/utils/growth_collector.py` with `OCIGrowthCollector` class
- **Comprehensive documentation**: `docs/GROWTH_COLLECTION.md` and `docs/GROWTH_COLLECTION_QUICK_REFERENCE.md`

#### Data Points Collected
1. **Tag Namespaces**: Top-level tag containers (via `oci iam tag-namespace list`)
2. **Tag Definitions**: Individual tags per namespace (via `oci iam tag list`)
3. **Tag Defaults**: Auto-tagging rules across compartments (via `oci iam tag-default list`)
4. **Resource Tags**: Tags applied to resources via Usage API
5. **Cost-Tracking Tags**: Cost breakdown by tag combinations via Usage API

#### New CLI Commands
```bash
# Growth collection only
./collector.sh <tenancy> <region> <from> <to> --only-growth

# Full collection with growth data
./collector.sh <tenancy> <region> <from> <to> --growth-collection
```

#### New Output Files
- `growth_collection_tags.json`: Complete JSON with all tag data
- `growth_collection_summary.txt`: Human-readable summary report

#### Use Cases
- **Cost Allocation**: Identify which tags drive the most cost
- **Chargeback**: Tag-based cost breakdown for departments/projects
- **Compliance Audits**: Ensure resources are properly tagged
- **Governance**: Review and validate auto-tagging rules
- **Trend Analysis**: Track tagging patterns over time

#### Performance
- Typical runtime: 2-5 minutes for a standard tenancy
- Multi-threaded processing for tag definitions
- Progress tracking for long-running operations
- Output files: 1-10 MB depending on tenancy size

#### Architecture Changes
```
src/
├── collector.py (enhanced with growth collection integration)
└── utils/
    ├── growth_collector.py (NEW)
    ├── api_executor.py
    ├── executor.py
    ├── progress.py
    ├── recommendations.py
    └── __init__.py

docs/
├── GROWTH_COLLECTION.md (NEW - comprehensive guide)
├── GROWTH_COLLECTION_QUICK_REFERENCE.md (NEW - quick reference)
├── ARCHITECTURE.md
├── CHANGELOG.md (updated)
└── ...
```

#### API Integration
- Uses `oci.identity.IdentityClient` for tag structure data
- Uses `oci.usage_api.UsageapiClient` for cost/tag correlations
- Efficient batching and parallel processing
- Smart caching to avoid redundant API calls

---

## Version 2.0 (November 2025)

### Major Refactoring
- **Decoupled Architecture**: Separated Python logic from Bash wrapper
- **Clean Code Structure**: Organized code into `src/` directory
- **Enhanced Documentation**: Added comprehensive docs in `docs/` directory

### New Features
- **Compute Instance Enrichment**: Automatically fetches shape and resourceName for compute instances
- **Dual API Strategy**: Uses both COST and USAGE query types for comprehensive data
- **Intelligent Caching**: Stores instance metadata to reduce API calls
- **Progress Reporting**: Real-time feedback during long-running operations
- **Virtual Environment Management**: Automatic Python dependency isolation

### Architecture Changes
```
Before v2.0:
cost_report/
├── collector.py (monolithic, ~400 lines)
├── collector.sh (embedded Python)
├── requirements.txt
└── various test files

After v2.0:
cost_report/
├── collector.sh (clean wrapper, ~90 lines)
├── src/
│   └── collector.py (OOP design, ~380 lines)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── QUICK_REFERENCE.md
│   └── CHANGELOG.md
├── output.json (placeholder)
├── output.csv (placeholder)
├── LICENSE
└── README.md
```

### Key Improvements

#### Code Quality
- Object-oriented design with `OCICostCollector` class
- Clear separation of concerns
- Type hints and documentation
- Error handling at multiple layers
- Comprehensive logging

#### User Experience
- Single entry point (`./collector.sh`)
- Automatic dependency management
- Clear progress indicators
- Detailed error messages
- Multiple output formats

#### Performance
- Metadata caching reduces redundant API calls
- Efficient DataFrame operations with pandas
- Optimized merge strategy
- Progress reporting every 10 instances

#### Maintainability
- Modular Python code
- Clean bash wrapper
- Comprehensive documentation
- Logical directory structure
- Version-controlled placeholders

### Files Removed
- `collector.py` (moved to `src/`)
- `collector_cloudshell.py` (functionality merged)
- `collector_cloudshell.sh` (functionality merged)
- `collector_merged.sh` (superseded by v2.0)
- `collector_simple.sh` (superseded by v2.0)
- `requirements.txt` (handled by wrapper)
- `README_CLOUDSHELL.md` (merged into main README)
- `test_auth.py` (development artifact)
- `test_response.py` (development artifact)

### Files Added
- `src/collector.py` - Main collector logic
- `docs/ARCHITECTURE.md` - System design documentation
- `docs/QUICK_REFERENCE.md` - Common usage patterns
- `docs/CHANGELOG.md` - This file
- `output.json` - Output placeholder
- `output.csv` - Output placeholder

### Files Modified
- `collector.sh` - Complete rewrite as wrapper
- `README.md` - Complete rewrite for v2.0
- `.gitignore` - Updated for new structure

### Files Preserved
- `LICENSE` - Unchanged (UPL 1.0)

### API Changes

#### OCI Usage API Integration
- **COST Query**: Gets service, skuName, resourceId, compartmentPath
- **USAGE Query**: Gets resourceId, platform, region, skuPartNumber
- **Merge Strategy**: Composite key (resourceId + timeUsageStarted)

#### OCI Compute API Integration
- **New**: Fetches instance metadata for enrichment
- **Fields**: shape, display-name
- **Caching**: Stores in `instance_metadata.json`

### Breaking Changes
- CLI remains compatible (same 4 parameters)
- Output filenames changed:
  - Old: `output.csv`, `out.json`
  - New: `output_merged.csv`, `output.csv`, `output.json`, `instance_metadata.json`

### Migration Guide

#### From v1.0 to v2.0

1. **Update Repository Structure**
   ```bash
   # Backup old files
   mkdir backup_v1
   cp *.py *.sh backup_v1/
   
   # Pull v2.0 changes
   git pull origin main
   ```

2. **Same CLI Usage**
   ```bash
   # Old (still works)
   ./collector.sh <tenancy> <region> <from> <to>
   
   # New (same command)
   ./collector.sh <tenancy> <region> <from> <to>
   ```

3. **New Output Files**
   - Main output is now `output_merged.csv` (was `output.csv`)
   - `output.csv` now contains basic merged data without enrichment
   - `instance_metadata.json` is a new cache file

### Known Issues
- Terminated instances fail metadata fetch (expected)
- Large date ranges (>3 months) may take 30+ minutes
- Rate limiting may occur with 1000+ instances

### Upcoming (v2.1)
- Parallel instance metadata fetching
- Support for additional resource types
- Excel output format
- Incremental update mode

---

## Version 1.0 (August 2022)

### Initial Release
- Basic cost data collection
- OCI SDK authentication
- Single API call approach
- JSON and CSV output
