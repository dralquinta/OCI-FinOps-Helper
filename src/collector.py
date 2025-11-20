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

from utils.progress import ProgressSpinner, ProgressTracker
from utils.executor import OCIMetadataFetcher
from utils.api_executor import OCIAPIExecutor


class OCICostCollector:
    """Collects cost and usage data from OCI and enriches with instance metadata."""
    
    def __init__(self, tenancy_ocid, home_region, from_date, to_date, output_dir='output'):
        self.tenancy_ocid = tenancy_ocid
        self.home_region = home_region
        self.from_date = from_date
        self.to_date = to_date
        self.api_endpoint = f"https://usageapi.{home_region}.oci.oraclecloud.com/20200107/usage"
        
        # Create output directory if it doesn't exist
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def make_api_call(self, query_type, group_by_fields, call_name):
        """Make an API call to OCI Usage API."""
        api_executor = OCIAPIExecutor(
            self.tenancy_ocid,
            self.home_region,
            output_dir=self.output_dir
        )
        
        return api_executor.make_api_call(
            query_type=query_type,
            group_by_fields=group_by_fields,
            call_name=call_name,
            from_date=self.from_date,
            to_date=self.to_date
        )
    
    def fetch_instance_metadata(self, instance_ids):
        """Fetch compute instance metadata using multi-threaded OCI CLI calls."""
        print(f"\n{'='*70}")
        print("🔄 Fetching Compute Instance Metadata")
        print(f"{'='*70}")
        print(f"Total instances to query: {len(instance_ids)}")
        print(f"Using multi-threaded executor for faster processing...\n")
        
        # Use OCIMetadataFetcher for parallel processing with built-in progress tracking
        fetcher = OCIMetadataFetcher(max_workers=10)
        instance_metadata, successful, failed = fetcher.fetch_metadata(instance_ids)
        
        print(f"\n✅ Successfully fetched {successful} instance metadata")
        if failed > 0:
            print(f"⚠️  Failed to fetch {failed} instances (may be terminated)")
        
        return instance_metadata
    
    def merge_and_enrich(self, data1, data2):
        """Merge two API responses and enrich with instance metadata."""
        print(f"\n{'='*70}")
        print(f"🔄 Merging and Enriching Data")
        print(f"{'='*70}")
        
        # Create spinner for merge operation
        spinner = ProgressSpinner("Saving and processing data...")
        spinner.start()
        
        # Save raw responses
        raw_output = {'call1': data1, 'call2': data2}
        out_file = self.output_dir / 'out.json'
        with open(out_file, 'w') as f:
            json.dump(raw_output, f, indent=2)
        print(f"✅ Raw JSON saved to {out_file}")
        
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
        output_csv = self.output_dir / 'output.csv'
        df_merged.to_csv(output_csv, index=False)
        print(f"✅ Basic merged CSV saved to {output_csv}")
        
        # Extract compute instance IDs
        compute_instances = df_merged[
            df_merged['resourceId'].str.contains('instance.oc1', na=False, case=False)
        ]['resourceId'].unique().tolist()
        
        spinner.stop()
        
        print(f"\n📊 Found {len(compute_instances)} unique compute instances")
        
        # Fetch instance metadata if we have instances
        if len(compute_instances) > 0:
            instance_metadata = self.fetch_instance_metadata(compute_instances)
            
            # Save metadata cache
            metadata_file = self.output_dir / 'instance_metadata.json'
            with open(metadata_file, 'w') as f:
                json.dump(instance_metadata, f, indent=2)
            print(f"✅ Instance metadata cached to {metadata_file}")
            
            # Enrich dataframe
            print(f"\n🔄 Enriching data with instance metadata...")
            spinner2 = ProgressSpinner("Processing enrichment...")
            spinner2.start()
            
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
            spinner2.stop()
            
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
        output_merged = self.output_dir / 'output_merged.csv'
        df_merged.to_csv(output_merged, index=False)
        print(f"✅ Final enriched CSV saved to {output_merged}")
        
        return df_merged
    
    def collect(self):
        """Main collection workflow."""
        print("="*70)
        print("🚀 OCI Cost Report Collector v2.0")
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
            self.merge_and_enrich(data1, data2)
            
            print(f"\n{'='*70}")
            print("🎉 SUCCESS!")
            print(f"{'='*70}")
            print(f"📁 Output directory: {self.output_dir.resolve()}")
            print("\n📋 Output files:")
            print(f"  - {self.output_dir}/output_merged.csv: Complete enriched data")
            print(f"  - {self.output_dir}/output.csv: Basic merged data (no enrichment)")
            print(f"  - {self.output_dir}/out.json: Raw API responses")
            print(f"  - {self.output_dir}/instance_metadata.json: Cached instance metadata")
            print(f"  - {self.output_dir}/request_*.json: API request payloads")
            
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
