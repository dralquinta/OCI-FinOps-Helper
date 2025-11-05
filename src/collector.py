#!/usr/bin/env python3
"""
OCI Cost Report Collector v2.0
Copyright (c) 2025 Oracle and/or its affiliates.
All rights reserved. The Universal Permissive License (UPL), Version 1.0
"""

import json
import sys
import subprocess
import time
import argparse
from pathlib import Path
import pandas as pd


class OCICostCollector:
    """Collects cost and usage data from OCI and enriches with instance metadata."""
    
    def __init__(self, tenancy_ocid, home_region, from_date, to_date):
        self.tenancy_ocid = tenancy_ocid
        self.home_region = home_region
        self.from_date = from_date
        self.to_date = to_date
        self.api_endpoint = f"https://usageapi.{home_region}.oci.oraclecloud.com/20200107/usage"
    
    def make_api_call(self, query_type, group_by_fields, call_name):
        """Make an API call to OCI Usage API."""
        print(f"\n{'='*70}")
        print(f"Making {call_name}")
        print(f"{'='*70}")
        
        # Build request body
        request_body = {
            "tenantId": self.tenancy_ocid,
            "timeUsageStarted": f"{self.from_date}T00:00:00Z",
            "timeUsageEnded": f"{self.to_date}T00:00:00Z",
            "granularity": "DAILY",
            "queryType": query_type,
            "groupBy": group_by_fields,
            "compartmentDepth": 4
        }
        
        # Save request body to temp file
        request_file = Path(f"request_{call_name}.json")
        with open(request_file, 'w') as f:
            json.dump(request_body, f, indent=2)
        
        # Execute OCI CLI raw-request
        try:
            result = subprocess.run(
                [
                    'oci', 'raw-request',
                    '--http-method', 'POST',
                    '--target-uri', self.api_endpoint,
                    '--request-body', f'file://{request_file}',
                    '--output', 'json'
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # Clean up temp file
            request_file.unlink()
            
            if result.returncode != 0:
                print(f"❌ API call failed: {result.stderr}")
                return None
            
            # Parse response
            response = json.loads(result.stdout)
            
            # Check for API errors
            if 'code' in response and 'message' in response:
                print(f"❌ API Error: {response.get('message')}")
                return None
            
            # Extract data
            api_data = response.get('data', response)
            
            if isinstance(api_data, dict) and 'items' in api_data:
                print(f"✅ Success: Retrieved {len(api_data['items'])} records")
                return api_data
            else:
                print(f"❌ Unexpected API response format")
                return None
        
        except subprocess.TimeoutExpired:
            print(f"❌ API call timeout after 300 seconds")
            return None
        except Exception as e:
            print(f"❌ API call failed: {e}")
            return None
    
    def fetch_instance_metadata(self, instance_ids):
        """Fetch compute instance metadata using OCI CLI."""
        print(f"\n{'='*70}")
        print(f"Fetching Compute Instance Metadata")
        print(f"{'='*70}")
        print(f"Total instances to query: {len(instance_ids)}")
        
        instance_metadata = {}
        successful = 0
        failed = 0
        
        for idx, instance_id in enumerate(instance_ids, 1):
            # Extract region from OCID (format: ocid1.instance.oc1.<region>.<unique_id>)
            parts = instance_id.split('.')
            if len(parts) < 4:
                print(f"⚠️  Cannot parse region from {instance_id}")
                failed += 1
                continue
            
            region = parts[3]
            
            # Show progress
            if idx % 10 == 0 or idx == 1:
                print(f"  Progress: {idx}/{len(instance_ids)} instances...")
            
            try:
                # Call OCI CLI to get instance details
                result = subprocess.run(
                    [
                        'oci', 'compute', 'instance', 'get',
                        '--instance-id', instance_id,
                        '--region', region,
                        '--output', 'json'
                    ],
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
                failed += 1
            except Exception as e:
                failed += 1
            
            # Small delay to avoid rate limiting
            if idx % 10 == 0:
                time.sleep(0.5)
        
        print(f"\n✅ Successfully fetched {successful} instance metadata")
        if failed > 0:
            print(f"⚠️  Failed to fetch {failed} instances (may be terminated)")
        
        return instance_metadata
    
    def merge_and_enrich(self, data1, data2):
        """Merge two API responses and enrich with instance metadata."""
        print(f"\n{'='*70}")
        print(f"Merging and Enriching Data")
        print(f"{'='*70}")
        
        # Save raw responses
        raw_output = {'call1': data1, 'call2': data2}
        with open('out.json', 'w') as f:
            json.dump(raw_output, f, indent=2)
        print("✅ Raw JSON saved to out.json")
        
        # Convert to DataFrames
        df1 = pd.DataFrame(data1['items'])
        df2 = pd.DataFrame(data2['items'])
        
        print(f"📋 First dataset (COST): {len(df1)} records")
        print(f"📋 Second dataset (USAGE): {len(df2)} records")
        
        # Create merge key (resourceId + timeUsageStarted)
        df1['merge_key'] = df1['resourceId'].astype(str) + '_' + df1['timeUsageStarted'].astype(str)
        df2['merge_key'] = df2['resourceId'].astype(str) + '_' + df2['timeUsageStarted'].astype(str)
        
        # Select columns from df2 to avoid duplicates
        df2_cols = ['merge_key', 'platform', 'region', 'skuPartNumber', 'shape', 'resourceName']
        df2_cols = [col for col in df2_cols if col in df2.columns]
        
        # Merge datasets
        df_merged = df1.merge(
            df2[df2_cols],
            on='merge_key',
            how='left',
            suffixes=('', '_from_call2')
        )
        
        # Drop merge key
        df_merged = df_merged.drop('merge_key', axis=1)
        
        print(f"✅ Merged dataset: {len(df_merged)} records with {len(df_merged.columns)} columns")
        
        # Save basic merged CSV
        df_merged.to_csv('output.csv', index=False)
        print(f"✅ Basic merged CSV saved to output.csv")
        
        # Extract compute instance IDs
        compute_instances = df_merged[
            df_merged['resourceId'].str.contains('instance.oc1', na=False, case=False)
        ]['resourceId'].unique().tolist()
        
        print(f"\n📊 Found {len(compute_instances)} unique compute instances")
        
        # Fetch instance metadata if we have instances
        if len(compute_instances) > 0:
            instance_metadata = self.fetch_instance_metadata(compute_instances)
            
            # Save metadata cache
            with open('instance_metadata.json', 'w') as f:
                json.dump(instance_metadata, f, indent=2)
            print(f"✅ Instance metadata cached to instance_metadata.json")
            
            # Enrich dataframe
            print(f"\nEnriching data with instance metadata...")
            
            def enrich_row(row):
                resource_id = row.get('resourceId', '')
                if resource_id in instance_metadata:
                    metadata = instance_metadata[resource_id]
                    if pd.isna(row.get('shape')) or row.get('shape') == '':
                        row['shape'] = metadata.get('shape', '')
                    if pd.isna(row.get('resourceName')) or row.get('resourceName') == '':
                        row['resourceName'] = metadata.get('resourceName', '')
                return row
            
            df_merged = df_merged.apply(enrich_row, axis=1)
            
            # Count enriched records
            enriched_shape = df_merged['shape'].notna().sum()
            enriched_name = df_merged['resourceName'].notna().sum()
            
            print(f"✅ Enrichment complete")
            print(f"📊 Enrichment results:")
            print(f"  - Records with shape: {enriched_shape}/{len(df_merged)}")
            print(f"  - Records with resourceName: {enriched_name}/{len(df_merged)}")
        else:
            print("⚠️  No compute instances found, skipping metadata enrichment")
        
        # Save final enriched CSV
        df_merged.to_csv('output_merged.csv', index=False)
        print(f"✅ Final enriched CSV saved to output_merged.csv")
        
        return df_merged
    
    def collect(self):
        """Main collection workflow."""
        print("="*70)
        print("OCI Cost Report Collector v2.0")
        print("="*70)
        print(f"Tenancy: {self.tenancy_ocid}")
        print(f"Region: {self.home_region}")
        print(f"From: {self.from_date}")
        print(f"To: {self.to_date}")
        
        # First API call - COST query with service details
        data1 = self.make_api_call(
            query_type="COST",
            group_by_fields=["service", "skuName", "resourceId", "compartmentPath"],
            call_name="COST_API_Call"
        )
        
        if data1 is None:
            print("\n❌ Failed to retrieve cost data")
            return False
        
        # Second API call - USAGE query with platform details
        data2 = self.make_api_call(
            query_type="USAGE",
            group_by_fields=["resourceId", "platform", "region", "skuPartNumber"],
            call_name="USAGE_API_Call"
        )
        
        if data2 is None:
            print("\n❌ Failed to retrieve usage data")
            return False
        
        # Merge and enrich
        try:
            df_final = self.merge_and_enrich(data1, data2)
            
            print(f"\n{'='*70}")
            print("SUCCESS!")
            print(f"{'='*70}")
            print("📁 Output files:")
            print("  - output_merged.csv: Complete enriched data")
            print("  - output.csv: Basic merged data (no enrichment)")
            print("  - out.json: Raw API responses")
            print("  - instance_metadata.json: Cached instance metadata")
            
            return True
        
        except Exception as e:
            print(f"\n❌ Merge and enrichment failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='OCI Cost Report Collector v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('tenancy_ocid', help='OCI Tenancy OCID')
    parser.add_argument('home_region', help='Home region (e.g., us-ashburn-1)')
    parser.add_argument('from_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('to_date', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Create collector and run
    collector = OCICostCollector(
        tenancy_ocid=args.tenancy_ocid,
        home_region=args.home_region,
        from_date=args.from_date,
        to_date=args.to_date
    )
    
    success = collector.collect()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
