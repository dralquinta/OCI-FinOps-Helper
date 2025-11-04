# OCI Cost Report Collector - Cloud Shell Enhanced

This enhanced version of the OCI Cost Report Collector is designed to work seamlessly in both OCI Cloud Shell and traditional environments.

## 🌟 New Features

- **Cloud Shell Auto-Detection**: Automatically detects if running in OCI Cloud Shell
- **Flexible Authentication**: Uses Cloud Shell instance principal or traditional OCI config
- **Enhanced Error Handling**: Better troubleshooting and error messages
- **Environment Validation**: Checks dependencies and authentication before running
- **Progress Reporting**: Real-time feedback during data processing

## 🚀 Quick Start (Cloud Shell)

1. **Open OCI Cloud Shell** from the OCI Console
2. **Clone or upload** this repository to Cloud Shell
3. **Run the enhanced script**:
   ```bash
   ./collector_cloudshell.sh ocid1.tenancy.oc1..YOUR_TENANCY_OCID us-ashburn-1 2025-11-01 2025-11-04
   ```

## 📋 Usage

### Command Syntax
```bash
./collector_cloudshell.sh <tenancy_ocid> <home_region> <from_date> <to_date>
```

### Parameters
- `tenancy_ocid`: Your OCI tenancy OCID (starts with `ocid1.tenancy.oc1..`)
- `home_region`: Your home region (e.g., `us-ashburn-1`, `us-phoenix-1`)
- `from_date`: Start date in YYYY-MM-DD format
- `to_date`: End date in YYYY-MM-DD format

### Examples
```bash
# Get cost data for the last 4 days
./collector_cloudshell.sh ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq us-ashburn-1 2025-11-01 2025-11-04

# Get cost data for October 2025
./collector_cloudshell.sh ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq us-ashburn-1 2025-10-01 2025-10-31

# Get cost data for a specific week
./collector_cloudshell.sh ocid1.tenancy.oc1..aaaaaaaaoi6b5sxlv4z773boczybqz3h2vspvvru42jysvizl77lky22ijaq us-phoenix-1 2025-10-20 2025-10-27
```

## 🔧 Environment Support

### OCI Cloud Shell ✅
- **Authentication**: Automatic via instance principal
- **Dependencies**: Pre-installed OCI CLI
- **Setup**: Ready to use immediately

### Local Development ✅
- **Authentication**: Uses `~/.oci/config` file
- **Dependencies**: Requires OCI SDK installation
- **Setup**: Traditional OCI CLI setup required

## 📊 Output Files

The script generates two output files:

1. **`output.csv`** - Structured CSV file for analysis
   - Import into Excel, Google Sheets, or BI tools
   - Contains columns: service, compartmentPath, computedAmount, currency, etc.

2. **`out.json`** - Raw JSON response from OCI Usage API
   - Complete API response with all metadata
   - Useful for custom processing or debugging

## 🔍 Data Structure

The CSV output includes these key columns:
- `tenantId`, `tenantName`
- `compartmentPath`, `compartmentName`
- `service`, `resourceName`
- `computedAmount`, `computedQuantity`
- `attributedCost`, `currency`
- `timeUsageStarted`, `timeUsageEnded`
- `region`, `tags`

## 🛠️ Troubleshooting

### Cloud Shell Issues

1. **Authentication Errors**:
   ```bash
   # Check if authenticated
   oci iam region list
   
   # Re-authenticate if needed
   oci session authenticate
   ```

2. **Permission Errors**:
   - Ensure your user has `inspect usage-reports` permission
   - Check tenancy-level policies for Usage API access

3. **Region Issues**:
   - Verify the home region is correct
   - Use the region where your tenancy was created

### Local Environment Issues

1. **Missing OCI Config**:
   ```bash
   # Check config file
   cat ~/.oci/config
   
   # Set up OCI CLI if missing
   oci setup config
   ```

2. **Python Dependencies**:
   ```bash
   # Install required packages
   pip3 install --user oci requests pandas
   ```

## 🚨 Important Notes

### Date Range Considerations
- **Large date ranges** (>30 days) may result in very large files
- **Start small** with a few days to test
- **October 2025** generated 114K+ records for a 4-day period

### Performance Tips
- Use shorter date ranges for faster processing
- Cloud Shell has timeout limits for long-running processes
- Consider breaking large requests into smaller chunks

### Authentication Requirements
- **Cloud Shell**: No setup required, uses instance principal
- **Local**: Requires proper OCI CLI configuration
- **Permissions**: User must have Usage API access rights

## 📈 Sample Output Size

For reference, here are typical output sizes:
- **4 days (Nov 1-4, 2025)**: 114,704 records, ~33MB CSV
- **1 month**: Expect 500K+ records, 100+ MB files
- **File formats**: JSON is larger than CSV due to formatting

## 🔗 API Information

This script uses the OCI Usage API:
- **Endpoint**: `https://usageapi.{region}.oci.oraclecloud.com/20200107/usage`
- **Method**: POST
- **Authentication**: OCI Signature Version 1
- **Documentation**: [OCI Usage API Docs](https://docs.oracle.com/en-us/iaas/api/#/en/usage/20200107/)

## 📝 Files in This Package

- `collector_cloudshell.py` - Enhanced Python script with Cloud Shell support
- `collector_cloudshell.sh` - Enhanced bash wrapper with environment detection
- `collector.py` - Original Python script (legacy)
- `collector.sh` - Original bash script (legacy)
- `requirements.txt` - Python dependencies
- `README_CLOUDSHELL.md` - This documentation

## 🤝 Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify your OCI permissions and configuration
3. Test with a small date range first
4. Review the debug output for specific error messages