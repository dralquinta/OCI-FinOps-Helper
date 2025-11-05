#!/bin/bash
# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl

# Enhanced script that makes two API calls and merges data to get complete information

echo "============== OCI Cost Report Collector (Merged Data) =============="

# Function to detect authentication method
detect_auth() {
    echo "============== Detecting Authentication Method =============="
    if oci iam region list --output table >/dev/null 2>&1; then
        echo "✅ OCI CLI authentication working"
        return 0
    else
        echo "❌ OCI CLI authentication failed"
        return 1
    fi
}

# Function to install Python dependencies
install_deps() {
    echo "============== Installing Python Dependencies =============="
    pip3 install --user requests pandas --quiet
    if [ $? -eq 0 ]; then
        echo "✅ Python dependencies installed"
    else
        echo "⚠️  Warning: Failed to install some dependencies"
    fi
}

# Main function
main() {
    if [ $# -lt 4 ]; then
        echo "❌ Usage: $0 <tenancy_ocid> <home_region> <from_date> <to_date>"
        echo ""
        echo "Example:"
        echo "  $0 ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-04"
        exit 1
    fi
    
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
    
    detect_auth || exit 1
    install_deps
    
    echo ""
    echo "============== Making First API Call (service, skuName, resourceId) =============="
    
    # First API call - get service, skuName, resourceId
    cat > request_body_1.json << EOF
{
    "tenantId": "$TENANCY_OCID",
    "timeUsageStarted": "${FROM_DATE}T00:00:00Z",
    "timeUsageEnded": "${TO_DATE}T00:00:00Z",
    "granularity": "DAILY",
    "queryType": "COST",
    "groupBy": ["service", "skuName", "resourceId", "compartmentPath"],
    "compartmentDepth": 4
}
EOF
    
    if oci raw-request \
        --http-method POST \
        --target-uri "https://usageapi.${HOME_REGION}.oci.oraclecloud.com/20200107/usage" \
        --request-body file://request_body_1.json \
        --output json > api_response_1.json 2>api_error_1.log; then
        echo "✅ First API call successful"
    else
        echo "❌ First API call failed"
        cat api_error_1.log
        exit 1
    fi
    
    echo ""
    echo "============== Making Second API Call (platform, region, skuPartNumber) =============="
    
    # Second API call - get platform, region, unit, skuPartNumber
    cat > request_body_2.json << EOF
{
    "tenantId": "$TENANCY_OCID",
    "timeUsageStarted": "${FROM_DATE}T00:00:00Z",
    "timeUsageEnded": "${TO_DATE}T00:00:00Z",
    "granularity": "DAILY",
    "queryType": "USAGE",
    "groupBy": [
        "resourceId",
        "platform",
        "region",
        "skuPartNumber"
    ],
    "compartmentDepth": 4
}
EOF
    
    if oci raw-request \
        --http-method POST \
        --target-uri "https://usageapi.${HOME_REGION}.oci.oraclecloud.com/20200107/usage" \
        --request-body file://request_body_2.json \
        --output json > api_response_2.json 2>api_error_2.log; then
        echo "✅ Second API call successful"
    else
        echo "❌ Second API call failed"
        cat api_error_2.log
        exit 1
    fi
    
    echo ""
    echo "============== Merging Data =============="
    
    # Python script to merge the two datasets
    python3 << 'PYTHON_SCRIPT'
import json
import pandas as pd
import sys

try:
    # Read first API response
    with open('api_response_1.json', 'r') as f:
        cli_response_1 = json.load(f)
    
    if 'code' in cli_response_1 and 'message' in cli_response_1:
        print(f"❌ API Error in first call: {cli_response_1.get('message')}")
        sys.exit(1)
    
    api_data_1 = cli_response_1.get('data', cli_response_1)
    
    # Read second API response
    with open('api_response_2.json', 'r') as f:
        cli_response_2 = json.load(f)
    
    if 'code' in cli_response_2 and 'message' in cli_response_2:
        print(f"❌ API Error in second call: {cli_response_2.get('message')}")
        sys.exit(1)
    
    api_data_2 = cli_response_2.get('data', cli_response_2)
    
    # Save raw responses
    with open('out.json', 'w') as f:
        json.dump({'call1': api_data_1, 'call2': api_data_2}, f, indent=2)
    print("✅ Raw JSON saved to out.json")
    
    # Process first dataset
    if isinstance(api_data_1, dict) and 'items' in api_data_1:
        df1 = pd.DataFrame(api_data_1['items'])
        print(f"📋 First dataset: {len(df1)} records")
    else:
        print("❌ Unexpected format in first API response")
        sys.exit(1)
    
    # Process second dataset
    if isinstance(api_data_2, dict) and 'items' in api_data_2:
        df2 = pd.DataFrame(api_data_2['items'])
        print(f"📋 Second dataset: {len(df2)} records")
    else:
        print("❌ Unexpected format in second API response")
        sys.exit(1)
    
    # Create merge key (resourceId + timeUsageStarted for precise matching)
    df1['merge_key'] = df1['resourceId'].astype(str) + '_' + df1['timeUsageStarted'].astype(str)
    df2['merge_key'] = df2['resourceId'].astype(str) + '_' + df2['timeUsageStarted'].astype(str)
    
    # Select specific columns from df2 to avoid duplicates
    df2_cols = ['merge_key', 'platform', 'region', 'skuPartNumber', 'shape', 'resourceName']
    # Only keep columns that exist in df2
    df2_cols = [col for col in df2_cols if col in df2.columns]
    
    # Merge datasets
    df_merged = df1.merge(
        df2[df2_cols],
        on='merge_key',
        how='left',
        suffixes=('', '_from_call2')
    )
    
    # Drop the merge key
    df_merged = df_merged.drop('merge_key', axis=1)
    
    print(f"✅ Merged dataset: {len(df_merged)} records with {len(df_merged.columns)} columns")
    print(f"📊 Key columns available:")
    key_cols = ['service', 'skuName', 'resourceId', 'shape', 'resourceName', 'platform', 'region', 'skuPartNumber']
    for col in key_cols:
        if col in df_merged.columns:
            non_null = df_merged[col].notna().sum()
            print(f"  - {col}: {non_null}/{len(df_merged)} populated")
    
    # Save merged CSV (before enrichment)
    df_merged.to_csv('output_merged.csv', index=False)
    print(f"✅ Merged CSV saved to output_merged.csv")
    
    # Also save the original first dataset for comparison
    df1_clean = df1.drop('merge_key', axis=1)
    df1_clean.to_csv('output.csv', index=False)
    print(f"✅ Original CSV saved to output.csv")
    
    # Extract unique compute instance IDs for metadata lookup
    compute_instances = df_merged[
        df_merged['resourceId'].str.contains('instance.oc1', na=False, case=False)
    ]['resourceId'].unique().tolist()
    
    print(f"\n📊 Found {len(compute_instances)} unique compute instances")
    
    # Save instance list for the next step
    with open('compute_instances.json', 'w') as f:
        json.dump(compute_instances, f)
    
    # Save the pre-enrichment merged data
    df_merged.to_csv('output_pre_enrichment.csv', index=False)

except Exception as e:
    print(f"❌ Merge failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to merge the API responses"
        exit 1
    fi
    
    echo ""
    echo "============== Fetching Compute Instance Metadata =============="
    
    # Check if we have compute instances to query
    if [ ! -f compute_instances.json ]; then
        echo "⚠️  No compute instances found, skipping metadata fetch"
    else
        # Fetch instance metadata using OCI CLI
        python3 << 'ENRICHMENT_SCRIPT'
import json
import subprocess
import pandas as pd
import sys
import time

try:
    # Load compute instance IDs
    with open('compute_instances.json', 'r') as f:
        instance_ids = json.load(f)
    
    if len(instance_ids) == 0:
        print("No compute instances to enrich")
        sys.exit(0)
    
    print(f"Fetching metadata for {len(instance_ids)} instances...")
    
    # Build instance metadata dictionary
    instance_metadata = {}
    successful = 0
    failed = 0
    
    for idx, instance_id in enumerate(instance_ids, 1):
        # Extract region from OCID
        # Format: ocid1.instance.oc1.<region>.<unique_id>
        parts = instance_id.split('.')
        if len(parts) >= 4:
            region = parts[3]
        else:
            print(f"⚠️  Cannot parse region from {instance_id}")
            failed += 1
            continue
        
        # Show progress every 10 instances
        if idx % 10 == 0 or idx == 1:
            print(f"  Progress: {idx}/{len(instance_ids)} instances...")
        
        try:
            # Call OCI CLI to get instance details
            cmd = [
                'oci', 'compute', 'instance', 'get',
                '--instance-id', instance_id,
                '--region', region,
                '--output', 'json'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                instance_data = json.loads(result.stdout)
                if 'data' in instance_data:
                    data = instance_data['data']
                    instance_metadata[instance_id] = {
                        'shape': data.get('shape', ''),
                        'resourceName': data.get('display-name', '')
                    }
                    successful += 1
                else:
                    failed += 1
            else:
                # Instance might be terminated or inaccessible
                failed += 1
        
        except subprocess.TimeoutExpired:
            print(f"⚠️  Timeout fetching {instance_id}")
            failed += 1
        except Exception as e:
            print(f"⚠️  Error fetching {instance_id}: {e}")
            failed += 1
        
        # Small delay to avoid rate limiting
        if idx % 10 == 0:
            time.sleep(0.5)
    
    print(f"\n✅ Successfully fetched {successful} instance metadata")
    if failed > 0:
        print(f"⚠️  Failed to fetch {failed} instances (may be terminated)")
    
    # Save metadata cache
    with open('instance_metadata.json', 'w') as f:
        json.dump(instance_metadata, f, indent=2)
    
    # Load the pre-enrichment merged data
    df = pd.read_csv('output_pre_enrichment.csv')
    
    # Enrich the dataframe with instance metadata
    def enrich_row(row):
        resource_id = row.get('resourceId', '')
        if resource_id in instance_metadata:
            metadata = instance_metadata[resource_id]
            # Update shape and resourceName if they're empty
            if pd.isna(row.get('shape')) or row.get('shape') == '':
                row['shape'] = metadata.get('shape', '')
            if pd.isna(row.get('resourceName')) or row.get('resourceName') == '':
                row['resourceName'] = metadata.get('resourceName', '')
        return row
    
    print("\nEnriching merged data with instance metadata...")
    df = df.apply(enrich_row, axis=1)
    
    # Save enriched data
    df.to_csv('output_merged.csv', index=False)
    
    # Count how many records were enriched
    enriched_shape = df['shape'].notna().sum()
    enriched_name = df['resourceName'].notna().sum()
    
    print(f"✅ Enriched data saved to output_merged.csv")
    print(f"📊 Enrichment results:")
    print(f"  - Records with shape: {enriched_shape}/{len(df)}")
    print(f"  - Records with resourceName: {enriched_name}/{len(df)}")

except Exception as e:
    print(f"❌ Enrichment failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
ENRICHMENT_SCRIPT
        
        if [ $? -ne 0 ]; then
            echo "⚠️  Enrichment failed, using merged data without instance metadata"
        fi
    fi
    
    echo ""
    echo "============== SUCCESS! =============="
    echo "📁 Output files:"
    ls -lh out.json output.csv output_merged.csv instance_metadata.json 2>/dev/null
    echo ""
    echo "💡 Files created:"
    echo "  - output_merged.csv: Complete merged data with instance metadata"
    echo "  - output.csv: Original first API call data"
    echo "  - out.json: Raw API responses"
    echo "  - instance_metadata.json: Cached instance metadata"
    echo ""
    echo "💡 Next steps:"
    echo "  - View merged data: head -5 output_merged.csv"
    echo "  - Check instance metadata: cat instance_metadata.json"
    echo "  - Download files using Cloud Shell's download menu"
    echo "  - Import output_merged.csv into Excel or Google Sheets"
    
    # Cleanup temporary files
    rm -f request_body_*.json api_response_*.json api_error_*.log compute_instances.json output_pre_enrichment.csv 2>/dev/null
}

main "$@"
