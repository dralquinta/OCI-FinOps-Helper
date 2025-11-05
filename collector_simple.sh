#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl

# Simple Cloud Shell compatible script

echo "============== OCI Cost Report Collector (Cloud Shell Edition) =============="

# Function to detect authentication method
detect_auth() {
    echo "============== Detecting Authentication Method =============="
    
    # Test OCI CLI first (works in Cloud Shell and configured local environments)
    if oci iam region list --output table >/dev/null 2>&1; then
        echo "✅ OCI CLI authentication working"
        return 0
    else
        echo "❌ OCI CLI authentication failed"
        echo ""
        echo "Troubleshooting:"
        echo "1. If you're in OCI Cloud Shell:"
        echo "   - Authentication should be automatic"
        echo "   - Try: oci session authenticate"
        echo ""
        echo "2. If you're in a local environment:"
        echo "   - Run: oci setup config"
        echo "   - Or check ~/.oci/config exists"
        echo ""
        return 1
    fi
}

# Function to install Python dependencies
install_deps() {
    echo "============== Installing Python Dependencies =============="
    
    # Install required packages using pip3
    echo "Installing requests and pandas..."
    pip3 install --user requests pandas --quiet
    
    if [ $? -eq 0 ]; then
        echo "✅ Python dependencies installed"
    else
        echo "⚠️  Warning: Failed to install some dependencies"
        echo "   This may still work if packages are already installed"
    fi
}

# Main function
main() {
    # Check arguments
    if [ $# -lt 4 ]; then
        echo "❌ Usage: $0 <tenancy_ocid> <home_region> <from_date> <to_date>"
        echo ""
        echo "Example:"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04"
        echo ""
        exit 1
    fi
    
    # Extract arguments
    TENANCY_OCID="$1"
    HOME_REGION="$2"
    FROM_DATE="$3"
    TO_DATE="$4"
    
    echo "Parameters:"
    echo "  Tenancy: $TENANCY_OCID"
    echo "  Region: $HOME_REGION"
    echo "  From: $FROM_DATE"
    echo "  To: $TO_DATE"
    echo ""
    
    # Check authentication
    if ! detect_auth; then
        exit 1
    fi
    
    # Install dependencies
    install_deps
    
    echo ""
    echo "============== Calling OCI Usage API =============="
    
    # Create the API call using OCI CLI raw-request
    # This works in both Cloud Shell and local environments with proper OCI CLI setup
    
    # Create request body
    cat > request_body.json << EOF
{
    "tenantId": "$TENANCY_OCID",
    "timeUsageStarted": "${FROM_DATE}T00:00:00Z",
    "timeUsageEnded": "${TO_DATE}T00:00:00Z",
    "granularity": "DAILY",
    "queryType": "COST",
    "groupBy": [
        "tagKey",
        "tagValue",
        "service",
        "compartmentPath",
        "shape",
        "resourceId",
        "resourceName",
        "skuPartNumber"
    ],
    "compartmentDepth": 4
}
EOF
    
    echo "✅ Request body created"
    echo "🌐 Calling Usage API..."
    
    # Make the API call using OCI CLI
    if oci raw-request \
        --http-method POST \
        --target-uri "https://usageapi.${HOME_REGION}.oci.oraclecloud.com/20200107/usage" \
        --request-body file://request_body.json \
        --output json > api_response.json 2>api_error.log; then
        
        echo "✅ API call successful!"
        
        # Check if we got data
        if [ -s api_response.json ]; then
            echo "📊 Processing response..."
            
            # Extract the actual data from OCI CLI response format
            # OCI CLI wraps the response in {"data": {...}}
            python3 << 'PYTHON_SCRIPT'
import json
import pandas as pd
import sys

try:
    # Read OCI CLI response
    with open('api_response.json', 'r') as f:
        cli_response = json.load(f)
    
    # Extract the actual API response data
    if 'data' in cli_response:
        api_data = cli_response['data']
    else:
        api_data = cli_response
    
    print(f"✅ JSON parsed. Type: {type(api_data)}")
    
    # Save raw API response
    with open('out.json', 'w') as f:
        json.dump(api_data, f, indent=2)
    print("✅ Raw JSON saved to out.json")
    
    # Process for CSV
    if isinstance(api_data, dict) and 'items' in api_data:
        items = api_data['items']
        print(f"📋 Found {len(items)} cost records")
        
        if items:
            df = pd.DataFrame(items)
            df.to_csv('output.csv', index=False)
            print(f"✅ CSV saved to output.csv with {len(df)} rows, {len(df.columns)} columns")
            
            # Show sample columns
            print(f"📊 Columns: {', '.join(df.columns[:8])}...")
        else:
            print("⚠️  No cost data found for the specified date range")
    else:
        print("⚠️  Unexpected response format")
        print(f"Response keys: {list(api_data.keys()) if isinstance(api_data, dict) else 'Not a dict'}")

except Exception as e:
    print(f"❌ Processing failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "============== SUCCESS! =============="
                echo "📁 Output files:"
                ls -lh out.json output.csv 2>/dev/null || echo "   Files may not exist if no data was found"
                echo ""
                echo "💡 Next steps:"
                echo "   - View CSV: head -5 output.csv"
                echo "   - Download files using Cloud Shell's download menu"
                echo "   - Import output.csv into Excel or Google Sheets"
            else
                echo "❌ Failed to process the API response"
            fi
        else
            echo "❌ Empty response received"
        fi
        
    else
        echo "❌ API call failed"
        echo "Error details:"
        cat api_error.log 2>/dev/null || echo "No error log available"
        exit 1
    fi
    
    # Cleanup
    rm -f request_body.json api_response.json api_error.log 2>/dev/null
}

# Run main function with all arguments
main "$@"