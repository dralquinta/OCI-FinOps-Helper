#!/usr/bin/env python3
"""
OCI Cost Report Collector v2.2.1
Copyright (c) 2025 Oracle and/or its affiliates.
All rights reserved. The Universal Permissive License (UPL), Version 1.0
"""

import json
import sys
import subprocess
import time
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

# Support both direct CLI execution and package imports for regression tests.
if __package__:
    from .utils.progress import ProgressSpinner, ProgressTracker
    from .utils.executor import OCIMetadataFetcher
    from .utils.api_executor import OCIAPIExecutor
    from .utils.recommendations import OCIRecommendationsFetcher
    from .utils.growth_collector import OCIGrowthCollector
else:
    from utils.progress import ProgressSpinner, ProgressTracker
    from utils.executor import OCIMetadataFetcher
    from utils.api_executor import OCIAPIExecutor
    from utils.recommendations import OCIRecommendationsFetcher
    from utils.growth_collector import OCIGrowthCollector


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
        cache_file = self.output_dir / 'instance_metadata_cache.json'
        now = time.time()
        entries = {}
        try:
            cache = json.loads(cache_file.read_text())
            if (isinstance(cache, dict) and cache.get('tenancy') == self.tenancy_ocid
                    and cache.get('region') == self.home_region
                    and isinstance(cache.get('entries'), dict)):
                entries = cache['entries']
        except (OSError, ValueError):
            pass
        fresh = {}
        for instance_id, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            fetched_at = entry.get('fetched_at')
            metadata = entry.get('metadata')
            if (isinstance(fetched_at, (int, float)) and 0 <= now - fetched_at < 86400
                    and isinstance(metadata, dict)
                    and all(isinstance(metadata.get(field, ''), str) for field in ('shape', 'resourceName'))):
                fresh[instance_id] = entry
        instance_ids = list(dict.fromkeys(instance_ids))
        instance_metadata = {iid: fresh[iid]['metadata'] for iid in instance_ids if iid in fresh}
        print(f"Reusing {len(instance_metadata)} fresh cached instance metadata entries")
        missing = [iid for iid in instance_ids if iid not in instance_metadata]
        successful, failed = 0, 0
        if missing:
            fetcher = OCIMetadataFetcher(max_workers=30)
            fetched, successful, failed = fetcher.fetch_metadata(missing)
            instance_metadata.update(fetched)
            fresh.update({iid: {'fetched_at': now, 'metadata': metadata} for iid, metadata in fetched.items()})
        temporary = cache_file.with_suffix('.tmp')
        temporary.write_text(json.dumps({'tenancy': self.tenancy_ocid, 'region': self.home_region, 'entries': fresh}))
        temporary.replace(cache_file)
        
        print(f"\n✅ Successfully fetched {successful} instance metadata")
        if failed > 0:
            print(f"⚠️  Failed to fetch {failed} instances (may be terminated)")
        
        return instance_metadata
    
    def merge_and_enrich(self, data1, data2, skip_enrichment=False):
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
        
        # USAGE has a different grain from COST: attach only unambiguous
        # metadata per resource/day, never multiply the monetary rows.
        keys = ['resourceId', 'timeUsageStarted']
        for frame in (df1, df2):
            for key in keys:
                if key not in frame:
                    frame[key] = pd.Series(index=frame.index, dtype=object)
        columns = [column for column in ('platform', 'region', 'skuPartNumber', 'shape', 'resourceName')
                   if column in df2]
        if columns and not df2.empty:
            metadata = df2.loc[df2[keys].notna().all(axis=1) & df2[keys].ne('').all(axis=1), keys + columns].copy()
            metadata[columns] = metadata[columns].replace('', pd.NA)
            grouped = metadata.groupby(keys, sort=False)
            unique_values = grouped[columns].nunique(dropna=True)
            collapsed = grouped[columns].first().where(unique_values.eq(1)).reset_index()
            df_merged = df1.merge(collapsed, on=keys, how='left', validate='many_to_one',
                                  suffixes=('', '_from_usage'))
            for column in columns:
                if column in df1:
                    missing = df_merged[column].isna() | df_merged[column].eq('')
                    df_merged.loc[missing, column] = df_merged.loc[missing, column + '_from_usage']
                    df_merged = df_merged.drop(columns=column + '_from_usage')
        else:
            df_merged = df1.copy()
        
        print(f"✅ Merged dataset: {len(df_merged)} records with {len(df_merged.columns)} columns")
        
        # Save basic merged CSV
        output_csv = self.output_dir / 'output.csv'
        df_merged.to_csv(output_csv, index=False)
        print(f"✅ Basic merged CSV saved to {output_csv}")
        
        # Extract compute instance IDs
        compute_instances = df_merged[
            df_merged['resourceId'].astype('string').str.contains('instance.oc1', na=False, case=False, regex=False)
        ]['resourceId'].unique().tolist()
        
        spinner.stop()
        
        print(f"\n📊 Found {len(compute_instances)} unique compute instances")
        
        # Fetch instance metadata if we have instances
        if len(compute_instances) > 0 and not skip_enrichment:
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
            
            for column in ('shape', 'resourceName'):
                if column not in df_merged:
                    df_merged[column] = pd.Series(index=df_merged.index, dtype=object)
                missing = df_merged[column].isna() | df_merged[column].eq('')
                values = {iid: metadata.get(column, '') for iid, metadata in instance_metadata.items()}
                mapped = df_merged['resourceId'].map(values)
                df_merged.loc[missing & mapped.notna(), column] = mapped
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
    
    def enrich_with_growth_data(self, df_merged, growth_results):
        """
        Enrich the merged cost/usage dataframe with growth collection data.
        
        Args:
            df_merged: Merged dataframe from cost/usage collection
            growth_results: Results from growth collection
            
        Returns:
            Enhanced dataframe with tag information
        """
        if not growth_results or 'growth_collector' not in growth_results:
            print("⚠️  No growth data available for enrichment")
            return df_merged
        
        print(f"\n{'='*70}")
        print("🌱 Enriching with Growth Collection Data")
        print(f"{'='*70}")
        
        growth_collector = growth_results['growth_collector']
        
        # Enrich with tag data
        if hasattr(growth_collector, 'enrich_dataframe_with_tags'):
            df_merged = growth_collector.enrich_dataframe_with_tags(df_merged)
            
            # Save enhanced version with tags
            output_with_tags = self.output_dir / 'output_with_tags.csv'
            df_merged.to_csv(output_with_tags, index=False)
            print(f"✅ Enhanced CSV with tags saved to {output_with_tags}")
        
        return df_merged
    
    def collect(self, skip_cost=False, skip_usage=False, skip_enrichment=False, 
                skip_recommendations=False, growth_collection=False, currency='USD'):
        """Main collection workflow with optional stage control."""
        print("="*70)
        print("🚀 OCI Cost Report Collector v2.2.1")
        print("="*70)
        print(f"Tenancy: {self.tenancy_ocid}")
        print(f"Region: {self.home_region}")
        print(f"From: {self.from_date}")
        print(f"To: {self.to_date}")
        print(f"Currency: {currency}")
        
        # Stage control
        if skip_cost or skip_usage or skip_enrichment or skip_recommendations or growth_collection:
            print(f"\n⚠️  Running with stage control:")
            if skip_cost:
                print("   - Skipping COST data collection")
            if skip_usage:
                print("   - Skipping USAGE data collection")
            if skip_enrichment:
                print("   - Skipping instance metadata enrichment")
            if skip_recommendations:
                print("   - Skipping recommendations collection")
            if growth_collection:
                print("   + GROWTH COLLECTION ADD-ON (tag enrichment)")
        
        growth_collector_obj = None
        
        data1 = None
        data2 = None
        df_merged = None
        collection_failed = False
        
        queries = []
        if not skip_cost:
            queries.append(("COST", ["service", "skuName", "resourceId", "compartmentPath"], "COST_API_Call"))
        if not skip_usage:
            queries.append(("USAGE", ["resourceId", "platform", "region", "skuPartNumber"], "USAGE_API_Call"))
        if queries:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(self.make_api_call, query_type=kind,
                           group_by_fields=fields, call_name=name)
                           for kind, fields, name in queries]
                for (kind, _, _), future in zip(queries, futures):
                    result = future.result()
                    if kind == "COST":
                        data1 = result
                    else:
                        data2 = result
                    if result is None:
                        print(f"Failed to retrieve {kind} data")
                        collection_failed = True

        # Merge and enrich
        if data1 is not None and data2 is not None:
            try:
                if skip_enrichment:
                    print("\n⚠️  Skipping enrichment - saving basic merged data only")
                    # Still need to do basic merge even if skipping enrichment
                df_merged = self.merge_and_enrich(data1, data2, skip_enrichment=True) if skip_enrichment else self.merge_and_enrich(data1, data2)
                
            except Exception as e:
                print(f"\n❌ Merge and enrichment failed: {e}")
                import traceback
                traceback.print_exc()
                collection_failed = True
        
        # Inventory collection must work even when cost/usage is skipped or fails.
        if growth_collection:
            growth_collector_obj = OCIGrowthCollector(
                tenancy_ocid=self.tenancy_ocid, home_region=self.home_region,
                output_dir=str(self.output_dir)
            )
            try:
                growth_collector_obj.collect_all(
                    from_date=self.from_date, to_date=self.to_date, cost_data=data1
                )
                if df_merged is not None:
                    df_merged = growth_collector_obj.enrich_dataframe_with_tags(df_merged)
                    df_merged.to_csv(self.output_dir / 'output_merged.csv', index=False)
            except Exception as error:
                print(f"⚠️ Growth/FinOps collection failed: {error}")
                collection_failed = True

        # Fetch cost-saving recommendations from Cloud Advisor
        if not skip_recommendations:
            print(f"\n{'='*70}")
            print("🔄 Fetching Cost-Saving Recommendations")
            print(f"{'='*70}")
            
            recommendations_fetcher = OCIRecommendationsFetcher(
                tenancy_ocid=self.tenancy_ocid,
                region=self.home_region,
                output_dir=str(self.output_dir),
                currency=currency
            )
            
            recommendations_file = recommendations_fetcher.fetch_and_save()
            
            if recommendations_file:
                print(f"✅ Recommendations successfully fetched and saved")
            else:
                print(f"⚠️  Warning: Could not fetch recommendations (may not have Cloud Advisor access)")
        
        # Success summary
        print(f"\n{'='*70}")
        print("⚠️ PARTIAL COLLECTION" if collection_failed else "🎉 SUCCESS!")
        print(f"{'='*70}")
        print(f"📁 Output directory: {self.output_dir.resolve()}")
        print("\n📋 Output files:")
        if not (skip_cost or skip_usage):
            if growth_collection:
                print(f"  - {self.output_dir}/output_merged.csv: Complete data enriched with tags")
            else:
                print(f"  - {self.output_dir}/output_merged.csv: Complete enriched data")
            print(f"  - {self.output_dir}/output.csv: Basic merged data (no enrichment)")
            print(f"  - {self.output_dir}/out.json: Raw API responses")
            print(f"  - {self.output_dir}/instance_metadata.json: Cached instance metadata")
        if not skip_recommendations:
            print(f"  - {self.output_dir}/recommendations.out: Actionable cost-saving recommendations")
            print(f"  - {self.output_dir}/recommendations.json: Raw recommendations JSON")
        if growth_collection:
            print(f"  - {self.output_dir}/growth_collection_tags.json: Complete tag analysis data")
            print(f"  - {self.output_dir}/growth_collection_summary.txt: Evidence summary")
            print(f"  - {self.output_dir}/finops_collection.json: Regional inventory and coverage")
            print(f"  - {self.output_dir}/finops_candidates.csv: Resource reduction review candidates")
            print(f"  - {self.output_dir}/finops_summary.txt: FinOps scope and candidate summary")
        if not (skip_cost or skip_usage):
            print(f"  - {self.output_dir}/request_*.json: API request payloads")
        
        return not collection_failed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='OCI Cost Report Collector v2.2.1',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('tenancy_ocid', help='OCI Tenancy OCID')
    parser.add_argument('home_region', help='Home region (e.g., us-ashburn-1)')
    parser.add_argument('from_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('to_date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--currency', default='USD', help='Requested currency metadata; Advisor estimates remain USD (no conversion)')
    parser.add_argument('--skip-cost', action='store_true', help='Skip cost data collection')
    parser.add_argument('--skip-usage', action='store_true', help='Skip usage data collection')
    parser.add_argument('--skip-enrichment', action='store_true', help='Skip instance metadata enrichment')
    parser.add_argument('--skip-recommendations', action='store_true', help='Skip recommendations collection')
    parser.add_argument('--only-recommendations', action='store_true', help='Only fetch recommendations (skip all other stages)')
    parser.add_argument('--growth-collection', action='store_true', 
                        help='Collect tags and regional FinOps inventory, attachments, and monitoring evidence')
    parser.add_argument('--only-growth', action='store_true', 
                        help='Only run growth collection (skip cost/usage data collection)')
    
    args = parser.parse_args()
    
    # Handle only-growth mode
    if args.only_growth:
        print("="*70)
        print("🚀 Running in GROWTH-ONLY mode")
        print("="*70)
        collector = OCICostCollector(
            tenancy_ocid=args.tenancy_ocid,
            home_region=args.home_region,
            from_date=args.from_date,
            to_date=args.to_date
        )
        success = collector.collect(
            skip_cost=True,
            skip_usage=True,
            skip_enrichment=True,
            skip_recommendations=True,
            growth_collection=True,
            currency=args.currency
        )
        sys.exit(0 if success else 1)
    
    # Create collector and run
    collector = OCICostCollector(
        tenancy_ocid=args.tenancy_ocid,
        home_region=args.home_region,
        from_date=args.from_date,
        to_date=args.to_date
    )
    
    # Handle only-recommendations mode
    if args.only_recommendations:
        print("="*70)
        print("🚀 Running in RECOMMENDATIONS-ONLY mode")
        print("="*70)
        recommendations_fetcher = OCIRecommendationsFetcher(
            tenancy_ocid=args.tenancy_ocid,
            region=args.home_region,
            output_dir=str(collector.output_dir),
            currency=args.currency
        )
        recommendations_file = recommendations_fetcher.fetch_and_save()
        if recommendations_file:
            print("\n✅ Recommendations fetched successfully!")
            sys.exit(0)
        else:
            print("\n❌ Failed to fetch recommendations")
            sys.exit(1)
    
    # Pass skip flags to collect method
    success = collector.collect(
        skip_cost=args.skip_cost,
        skip_usage=args.skip_usage,
        skip_enrichment=args.skip_enrichment,
        skip_recommendations=args.skip_recommendations,
        growth_collection=args.growth_collection,
        currency=args.currency
    )
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
