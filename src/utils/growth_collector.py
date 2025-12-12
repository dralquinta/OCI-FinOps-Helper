"""
Growth Collection utilities for OCI tag-related data.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from .progress import ProgressSpinner, ProgressTracker


class OCIGrowthCollector:
    """Collects tag-related data for growth analysis from OCI."""
    
    def __init__(self, tenancy_ocid, home_region, output_dir='output', max_workers_tags=20, max_workers_compartments=30):
        """
        Initialize Growth Collector.
        
        Args:
            tenancy_ocid: OCI Tenancy OCID
            home_region: Home region (e.g., us-ashburn-1)
            output_dir: Output directory for collected data
            max_workers_tags: Max parallel workers for tag definitions (default: 10)
            max_workers_compartments: Max parallel workers for compartment scanning (default: 20)
        """
        self.tenancy_ocid = tenancy_ocid
        self.home_region = home_region
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance settings
        self.max_workers_tags = max_workers_tags
        self.max_workers_compartments = max_workers_compartments
        
        # Initialize data storage
        self.tag_namespaces = []
        self.tag_definitions = {}
        self.tag_defaults = []
        self.compartments = []
        
    def _execute_oci_command(self, command, description):
        """
        Execute an OCI CLI command with progress tracking.
        
        Args:
            command: List containing the OCI CLI command and arguments
            description: Description for progress spinner
            
        Returns:
            Parsed JSON response or None if failed
        """
        spinner = ProgressSpinner(description)
        spinner.start()
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            spinner.stop()
            
            if result.returncode != 0:
                print(f"❌ Command failed: {result.stderr[:200]}")
                return None
            
            # Parse JSON response
            response = json.loads(result.stdout)
            
            # Check for data field (standard OCI CLI response format)
            if 'data' in response:
                return response['data']
            
            return response
            
        except subprocess.TimeoutExpired:
            spinner.stop()
            print(f"⏱️  Command timed out")
            return None
        except json.JSONDecodeError as e:
            spinner.stop()
            print(f"❌ Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            spinner.stop()
            print(f"❌ Unexpected error: {e}")
            return None
    
    def _get_all_compartments(self):
        """
        Fetch all compartments in the tenancy recursively.
        
        Returns:
            List of compartment OCIDs
        """
        print(f"\n{'='*70}")
        print("📦 Discovering Compartments")
        print(f"{'='*70}")
        
        command = [
            'oci', 'iam', 'compartment', 'list',
            '--compartment-id', self.tenancy_ocid,
            '--compartment-id-in-subtree', 'true',
            '--all',
            '--output', 'json'
        ]
        
        data = self._execute_oci_command(
            command,
            "🔍 Fetching compartments..."
        )
        
        if data:
            # Include root tenancy as a compartment
            self.compartments = [self.tenancy_ocid]
            self.compartments.extend([comp['id'] for comp in data if comp.get('lifecycle-state') == 'ACTIVE'])
            print(f"✅ Found {len(self.compartments)} compartments (including root)")
        else:
            print("⚠️  Using root tenancy only")
            self.compartments = [self.tenancy_ocid]
        
        return self.compartments
    
    def collect_tag_namespaces(self):
        """
        Collect all tag namespaces from the tenancy.
        Data Point: Tag Namespaces
        API: oci.identity.IdentityClient.list_tag_namespaces(compartment_id)
        Purpose: Understand tagging structure
        
        Returns:
            List of tag namespace data
        """
        print(f"\n{'='*70}")
        print("🏷️  Collecting Tag Namespaces")
        print(f"{'='*70}")
        
        command = [
            'oci', 'iam', 'tag-namespace', 'list',
            '--compartment-id', self.tenancy_ocid,
            '--all',
            '--output', 'json'
        ]
        
        data = self._execute_oci_command(
            command,
            "🔍 Fetching tag namespaces..."
        )
        
        if data:
            self.tag_namespaces = data
            print(f"✅ Collected {len(self.tag_namespaces)} tag namespaces")
            
            # Display summary
            for ns in self.tag_namespaces[:5]:  # Show first 5
                print(f"  📋 {ns.get('name', 'N/A')} - {ns.get('description', 'No description')}")
            if len(self.tag_namespaces) > 5:
                print(f"  ... and {len(self.tag_namespaces) - 5} more")
        else:
            print("⚠️  No tag namespaces found or error occurred")
            self.tag_namespaces = []
        
        return self.tag_namespaces
    
    def _fetch_tags_for_namespace(self, ns_id, ns_name):
        """
        Fetch tags for a single namespace (helper for parallel processing).
        
        Args:
            ns_id: Tag namespace OCID
            ns_name: Tag namespace name
            
        Returns:
            Tuple of (ns_id, dict with namespace_name and tags)
        """
        command = [
            'oci', 'iam', 'tag', 'list',
            '--tag-namespace-id', ns_id,
            '--all',
            '--output', 'json'
        ]
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30  # Reduced from 60s
            )
            
            if result.returncode == 0:
                response = json.loads(result.stdout)
                data = response.get('data', [])
                return ns_id, {
                    'namespace_name': ns_name,
                    'tags': data
                }
            else:
                return ns_id, {
                    'namespace_name': ns_name,
                    'tags': [],
                    'error': result.stderr[:100]
                }
        except Exception as e:
            return ns_id, {
                'namespace_name': ns_name,
                'tags': [],
                'error': str(e)
            }
    
    def collect_tag_definitions(self):
        """
        Collect all tag definitions (tags) for each namespace in parallel.
        Data Point: Tag Definitions
        API: oci.identity.IdentityClient.list_tags(tag_namespace_id)
        Purpose: Available tags per namespace
        
        Returns:
            Dictionary mapping namespace_id to list of tag definitions
        """
        print(f"\n{'='*70}")
        print("🔖 Collecting Tag Definitions")
        print(f"{'='*70}")
        
        if not self.tag_namespaces:
            print("⚠️  No tag namespaces available. Run collect_tag_namespaces() first.")
            return {}
        
        print(f"Using {self.max_workers_tags} parallel workers for faster collection...")
        
        tracker = ProgressTracker(len(self.tag_namespaces))
        completed = 0
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.max_workers_tags) as executor:
            # Submit all tasks
            future_to_namespace = {
                executor.submit(self._fetch_tags_for_namespace, ns.get('id'), ns.get('name', 'Unknown')): ns
                for ns in self.tag_namespaces
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_namespace):
                ns_id, ns_data = future.result()
                completed += 1
                
                self.tag_definitions[ns_id] = ns_data
                
                # Update progress display
                tracker.update(completed)
        
        tracker.finish()
        
        # Calculate total tags
        total_tags = sum(len(ns_data.get('tags', [])) for ns_data in self.tag_definitions.values())
        print(f"✅ Collected {total_tags} tag definitions across {len(self.tag_definitions)} namespaces")
        
        return self.tag_definitions
    
    def _fetch_tag_defaults_for_compartment(self, comp_id):
        """
        Fetch tag defaults for a single compartment (helper for parallel processing).
        
        Args:
            comp_id: Compartment OCID
            
        Returns:
            Tuple of (comp_id, list of tag defaults or None if error)
        """
        command = [
            'oci', 'iam', 'tag-default', 'list',
            '--compartment-id', comp_id,
            '--all',
            '--output', 'json'
        ]
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30  # Reduced from 60s for faster failure
            )
            
            if result.returncode == 0:
                response = json.loads(result.stdout)
                data = response.get('data', [])
                
                # Add compartment context to each tag default
                for td in data:
                    td['source_compartment_id'] = comp_id
                
                return comp_id, data
            else:
                return comp_id, None
                
        except Exception:
            return comp_id, None
    
    def collect_tag_defaults(self):
        """
        Collect tag defaults (auto-tagging rules) for all compartments in parallel.
        Data Point: Tag Defaults
        API: oci.identity.IdentityClient.list_tag_defaults(compartment_id)
        Purpose: Auto-tagging rules
        
        Returns:
            List of tag defaults
        """
        print(f"\n{'='*70}")
        print("⚙️  Collecting Tag Defaults (Auto-tagging Rules)")
        print(f"{'='*70}")
        print(f"Using {self.max_workers_compartments} parallel workers for faster collection...")
        
        if not self.compartments:
            self._get_all_compartments()
        
        all_tag_defaults = []
        tracker = ProgressTracker(len(self.compartments))
        completed = 0
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.max_workers_compartments) as executor:
            # Submit all tasks
            future_to_compartment = {
                executor.submit(self._fetch_tag_defaults_for_compartment, comp_id): comp_id
                for comp_id in self.compartments
            }
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_compartment):
                _, tag_defaults = future.result()
                completed += 1
                
                if tag_defaults is not None and len(tag_defaults) > 0:
                    all_tag_defaults.extend(tag_defaults)
                
                # Update progress display
                tracker.update(completed)
        
        tracker.finish()
        
        self.tag_defaults = all_tag_defaults
        print(f"✅ Collected {len(self.tag_defaults)} tag defaults")
        
        if self.tag_defaults:
            print("\n📋 Sample tag defaults:")
            for td in self.tag_defaults[:3]:
                print(f"  🏷️  {td.get('tag-definition-name', 'N/A')} = {td.get('value', 'N/A')}")
            if len(self.tag_defaults) > 3:
                print(f"  ... and {len(self.tag_defaults) - 3} more")
        
        return self.tag_defaults
    
    def collect_resource_tags(self, from_date, to_date):
        """
        Collect defined tags and freeform tags from resources via Usage API.
        Data Points: Defined Tags on Resources, Freeform Tags on Resources
        API: Each resource API returns defined_tags and freeform_tags
        Purpose: Cost allocation & chargeback, Custom metadata tracking
        
        Note: This collects tags from the Usage API which already includes
        tag information for resources. We'll aggregate unique tag keys used.
        
        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary with defined_tags and freeform_tags statistics
        """
        print(f"\n{'='*70}")
        print("🔍 Collecting Resource Tags from Usage Data")
        print(f"{'='*70}")
        
        # Build request to get usage data with tags
        request_body = {
            "tenantId": self.tenancy_ocid,
            "timeUsageStarted": f"{from_date}T00:00:00Z",
            "timeUsageEnded": f"{to_date}T00:00:00Z",
            "granularity": "DAILY",
            "queryType": "USAGE",
            "groupBy": ["resourceId", "tagNamespace", "tagKey", "tagValue"],
            "compartmentDepth": 4
        }
        
        # Save request body
        request_file = self.output_dir / "request_resource_tags.json"
        with open(request_file, 'w') as f:
            json.dump(request_body, f, indent=2)
        
        api_endpoint = f"https://usageapi.{self.home_region}.oci.oraclecloud.com/20200107/usage"
        
        command = [
            'oci', 'raw-request',
            '--http-method', 'POST',
            '--target-uri', api_endpoint,
            '--request-body', f'file://{request_file}',
            '--output', 'json'
        ]
        
        data = self._execute_oci_command(
            command,
            "🌐 Fetching resource tags from Usage API..."
        )
        
        # Clean up request file
        if request_file.exists():
            request_file.unlink()
        
        if data and 'items' in data:
            items = data['items']
            
            # Aggregate unique tag namespaces, keys, and values
            tag_stats = {
                'total_records': len(items),
                'unique_tag_namespaces': set(),
                'unique_tag_keys': set(),
                'tag_namespace_key_pairs': set(),
                'resources_with_tags': set()
            }
            
            # Build resource-to-tags mapping for enrichment
            self._resource_tag_map = {}
            
            for item in items:
                resource_id = item.get('resourceId', '')
                
                # Tags come in a nested 'tags' array from the Usage API
                tags_array = item.get('tags', [])
                
                if resource_id and tags_array:
                    # Initialize resource entry if not exists
                    if resource_id not in self._resource_tag_map:
                        self._resource_tag_map[resource_id] = {
                            'tags': [],
                            'namespaces': set()
                        }
                    
                    # Process each tag in the array
                    for tag_dict in tags_array:
                        if not isinstance(tag_dict, dict):
                            continue
                            
                        tag_namespace = tag_dict.get('namespace', '')
                        tag_key = tag_dict.get('key', '')
                        tag_value = tag_dict.get('value', '')
                        
                        # Skip tags with None/empty values
                        if not tag_namespace or not tag_key:
                            continue
                        
                        # Update statistics
                        tag_stats['unique_tag_namespaces'].add(tag_namespace)
                        tag_stats['unique_tag_keys'].add(tag_key)
                        tag_stats['tag_namespace_key_pairs'].add(
                            f"{tag_namespace}.{tag_key}"
                        )
                        tag_stats['resources_with_tags'].add(resource_id)
                        
                        # Add to resource tag map
                        self._resource_tag_map[resource_id]['tags'].append({
                            'namespace': tag_namespace,
                            'key': tag_key,
                            'value': tag_value
                        })
                        self._resource_tag_map[resource_id]['namespaces'].add(tag_namespace)
            
            # Convert sets to lists for JSON serialization
            for resource_id in self._resource_tag_map:
                self._resource_tag_map[resource_id]['namespaces'] = list(
                    self._resource_tag_map[resource_id]['namespaces']
                )
            
            # Convert sets to lists for JSON serialization
            result = {
                'total_records': tag_stats['total_records'],
                'unique_tag_namespaces': sorted(list(tag_stats['unique_tag_namespaces'])),
                'unique_tag_keys': sorted(list(tag_stats['unique_tag_keys'])),
                'tag_namespace_key_pairs': sorted(list(tag_stats['tag_namespace_key_pairs'])),
                'resources_with_tags_count': len(tag_stats['resources_with_tags']),
                'raw_data': items[:1000]  # Store first 1000 records
            }
            
            print(f"✅ Collected tag data from {result['total_records']} usage records")
            print(f"  📊 Unique tag namespaces: {len(result['unique_tag_namespaces'])}")
            print(f"  📊 Unique tag keys: {len(result['unique_tag_keys'])}")
            print(f"  📊 Resources with tags: {result['resources_with_tags_count']}")
            
            return result
        else:
            print("⚠️  No resource tag data found")
            return None
    
    def collect_cost_tracking_tags(self, from_date, to_date):
        """
        Collect cost-tracking tags - tags with associated cost data.
        Data Point: Cost-Tracking Tags
        API: oci.usage_api.UsageapiClient with tagNamespace, tagKey, tagValue in groupBy
        Purpose: Tag-based cost breakdown
        
        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            Cost data grouped by tags
        """
        print(f"\n{'='*70}")
        print("💰 Collecting Cost-Tracking Tags")
        print(f"{'='*70}")
        
        # Build request to get cost data grouped by tags
        request_body = {
            "tenantId": self.tenancy_ocid,
            "timeUsageStarted": f"{from_date}T00:00:00Z",
            "timeUsageEnded": f"{to_date}T00:00:00Z",
            "granularity": "DAILY",
            "queryType": "COST",
            "groupBy": ["tagNamespace", "tagKey", "tagValue", "service"],
            "compartmentDepth": 4
        }
        
        # Save request body
        request_file = self.output_dir / "request_cost_tracking_tags.json"
        with open(request_file, 'w') as f:
            json.dump(request_body, f, indent=2)
        
        api_endpoint = f"https://usageapi.{self.home_region}.oci.oraclecloud.com/20200107/usage"
        
        command = [
            'oci', 'raw-request',
            '--http-method', 'POST',
            '--target-uri', api_endpoint,
            '--request-body', f'file://{request_file}',
            '--output', 'json'
        ]
        
        data = self._execute_oci_command(
            command,
            "🌐 Fetching cost data by tags from Usage API..."
        )
        
        # Clean up request file
        if request_file.exists():
            request_file.unlink()
        
        if data and 'items' in data:
            items = data['items']
            
            # Aggregate cost by tag
            cost_by_tag = {}
            total_cost = 0
            
            for item in items:
                tag_ns = item.get('tagNamespace', 'untagged')
                tag_key = item.get('tagKey', 'untagged')
                tag_value = item.get('tagValue', 'untagged')
                cost = float(item.get('computedAmount', 0))
                
                tag_full = f"{tag_ns}.{tag_key}={tag_value}"
                
                if tag_full not in cost_by_tag:
                    cost_by_tag[tag_full] = {
                        'namespace': tag_ns,
                        'key': tag_key,
                        'value': tag_value,
                        'total_cost': 0,
                        'services': {}
                    }
                
                cost_by_tag[tag_full]['total_cost'] += cost
                total_cost += cost
                
                service = item.get('service', 'Unknown')
                if service not in cost_by_tag[tag_full]['services']:
                    cost_by_tag[tag_full]['services'][service] = 0
                cost_by_tag[tag_full]['services'][service] += cost
            
            # Sort by cost descending
            sorted_tags = sorted(
                cost_by_tag.items(),
                key=lambda x: x[1]['total_cost'],
                reverse=True
            )
            
            result = {
                'total_cost': total_cost,
                'unique_tag_combinations': len(cost_by_tag),
                'cost_by_tag': dict(sorted_tags),
                'raw_data': items[:1000]  # Store first 1000 records
            }
            
            print(f"✅ Collected cost data for {len(cost_by_tag)} unique tag combinations")
            print(f"  💵 Total cost tracked: ${total_cost:,.2f}")
            
            # Show top 5 cost-driving tags
            print("\n📊 Top 5 cost-driving tag combinations:")
            for tag_full, tag_data in sorted_tags[:5]:
                print(f"  💰 {tag_full}: ${tag_data['total_cost']:,.2f}")
            
            return result
        else:
            print("⚠️  No cost-tracking tag data found")
            return None
    
    def enrich_dataframe_with_tags(self, df, resource_id_column='resourceId'):
        """
        Enrich a dataframe with tag information from collected growth data.
        
        This method adds tag-related columns to the existing cost/usage dataframe,
        enabling tag-based analysis and chargeback reporting.
        
        Args:
            df: pandas DataFrame with resource data
            resource_id_column: Name of column containing resource OCIDs (default: 'resourceId')
            
        Returns:
            Enhanced DataFrame with additional tag columns:
            - has_tags: Boolean indicating if resource has any tags
            - tag_count: Number of tags on the resource
            - tag_namespaces: List of tag namespaces used
            - primary_cost_center: Primary cost center tag (if exists)
            - primary_environment: Primary environment tag (if exists)
        """
        if not hasattr(self, '_resource_tag_map'):
            print("⚠️  Warning: Tag data not collected. Run collect_resource_tags() first.")
            return df
        
        print(f"\n{'='*70}")
        print("🔖 Enriching DataFrame with Tag Information")
        print(f"{'='*70}")
        print(f"Input DataFrame: {len(df)} rows")
        
        # Initialize new columns
        df['has_tags'] = False
        df['tag_count'] = 0
        df['tag_namespaces'] = ''
        df['primary_cost_center'] = ''
        df['primary_environment'] = ''
        
        # Replace the tags column if it exists (from Usage API with None values)
        if 'tags' in df.columns:
            df['tags'] = None
        
        # Enrich each row
        enriched_count = 0
        for idx, row in df.iterrows():
            resource_id = row.get(resource_id_column, '')
            if resource_id and resource_id in self._resource_tag_map:
                tag_info = self._resource_tag_map[resource_id]
                tags_list = tag_info.get('tags', [])
                
                df.at[idx, 'has_tags'] = True
                df.at[idx, 'tag_count'] = len(tags_list)
                df.at[idx, 'tag_namespaces'] = ','.join(tag_info.get('namespaces', []))
                
                # Store the actual tags list as JSON string
                if tags_list:
                    df.at[idx, 'tags'] = json.dumps(tags_list)
                
                # Extract common tags
                for tag in tags_list:
                    key = tag.get('key', '')
                    value = tag.get('value', '')
                    
                    # Map common cost center tags
                    if key.lower() in ['costcenter', 'cost-center', 'cost_center', 'department']:
                        df.at[idx, 'primary_cost_center'] = value
                    
                    # Map common environment tags
                    if key.lower() in ['environment', 'env', 'stage']:
                        df.at[idx, 'primary_environment'] = value
                
                enriched_count += 1
        
        print(f"✅ Enriched {enriched_count}/{len(df)} rows with tag information")
        print(f"  - Resources with tags: {df['has_tags'].sum()}")
        print(f"  - Average tags per resource: {df['tag_count'].mean():.1f}")
        
        return df
    
    def get_enrichment_summary(self):
        """
        Get summary statistics for enrichment operations.
        
        Returns:
            Dictionary with enrichment statistics
        """
        if not hasattr(self, '_resource_tag_map'):
            return {'error': 'No tag data collected'}
        
        return {
            'total_resources_with_tags': len(self._resource_tag_map),
            'unique_tag_namespaces': len(set(
                ns for res in self._resource_tag_map.values() 
                for ns in res.get('namespaces', [])
            )),
            'total_tags_collected': sum(
                len(res.get('tags', [])) 
                for res in self._resource_tag_map.values()
            )
        }
    
    def collect_performance_metrics(self, from_date, to_date):
        """
        Collect performance metrics from OCI Monitoring service.
        Data Points:
        - Compute: CpuUtilization, MemoryUtilization (Resource saturation)
        - Storage: VolumeReadThroughput, VolumeWriteThroughput (IOPS usage)
        - Network: NetworksBytesIn, NetworksBytesOut (Bandwidth usage)
        - Database: CpuUtilization, StorageUtilization (DB resource usage)
        - Load Balancer: ConnectionsCount (Load balancer load)
        
        API: oci.monitoring.MonitoringClient.summarize_metrics_data()
        Purpose: Identify resource saturation, capacity planning, optimization
        
        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary with performance metrics by resource type
        """
        print(f"\n{'='*70}")
        print("📊 Collecting Performance Metrics")
        print(f"{'='*70}")
        
        # Define metrics to collect for each namespace
        metrics_config = {
            'oci_computeagent': {
                'display_name': 'Compute Instances',
                'metrics': ['CpuUtilization', 'MemoryUtilization']
            },
            'oci_blockstore': {
                'display_name': 'Block Volumes',
                'metrics': ['VolumeReadThroughput', 'VolumeWriteThroughput']
            },
            'oci_vcn': {
                'display_name': 'Network (VCN)',
                'metrics': ['VnicToNetworkBytes', 'VnicFromNetworkBytes']
            },
            'oci_database': {
                'display_name': 'Databases',
                'metrics': ['CpuUtilization', 'StorageUtilization']
            },
            'oci_lbaas': {
                'display_name': 'Load Balancers',
                'metrics': ['ActiveConnections', 'ConnectionCount']
            }
        }
        
        all_metrics = {}
        
        for namespace, config in metrics_config.items():
            print(f"\n🔍 Collecting {config['display_name']} metrics...")
            
            namespace_metrics = {
                'display_name': config['display_name'],
                'metrics': {}
            }
            
            for metric_name in config['metrics']:
                # Build query for this metric
                query = f"{metric_name}[1m].mean()"
                
                # Build request body for summarize_metrics_data
                request_body = {
                    "namespace": namespace,
                    "query": query,
                    "startTime": f"{from_date}T00:00:00.000Z",
                    "endTime": f"{to_date}T23:59:59.999Z",
                    "resolution": "1h"
                }
                
                # Save request body
                request_file = self.output_dir / f"request_metrics_{namespace}_{metric_name}.json"
                with open(request_file, 'w') as f:
                    json.dump(request_body, f, indent=2)
                
                api_endpoint = f"https://telemetry.{self.home_region}.oraclecloud.com/20180401/metrics/actions/summarizeMetricsData"
                
                command = [
                    'oci', 'raw-request',
                    '--http-method', 'POST',
                    '--target-uri', api_endpoint,
                    '--request-body', f'file://{request_file}',
                    '--output', 'json'
                ]
                
                data = self._execute_oci_command(
                    command,
                    f"  📈 Fetching {metric_name}..."
                )
                
                # Clean up request file
                if request_file.exists():
                    request_file.unlink()
                
                if data and isinstance(data, list) and len(data) > 0:
                    # Store metric data
                    namespace_metrics['metrics'][metric_name] = {
                        'data_points': len(data),
                        'samples': data[:100]  # Store first 100 samples
                    }
                    print(f"    ✅ Collected {len(data)} data points for {metric_name}")
                else:
                    namespace_metrics['metrics'][metric_name] = {
                        'data_points': 0,
                        'samples': []
                    }
                    print(f"    ⚠️  No data found for {metric_name}")
            
            all_metrics[namespace] = namespace_metrics
        
        result = {
            'collection_period': {
                'from_date': from_date,
                'to_date': to_date
            },
            'metrics_by_namespace': all_metrics
        }
        
        print("\n✅ Performance metrics collection complete")
        return result
    
    def collect_audit_events(self, from_date, to_date):
        """
        Collect audit events from OCI Audit service.
        Data Point: Audit Events
        API: oci.audit.AuditClient.list_events(compartment_id, start_time, end_time)
        Purpose: Track resource lifecycle patterns, identify who did what and when
        
        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary with audit events summary and patterns
        """
        print(f"\n{'='*70}")
        print("🔍 Collecting Audit Events")
        print(f"{'='*70}")
        
        if not self.compartments:
            self._get_all_compartments()
        
        all_events = []
        event_stats = {
            'total_events': 0,
            'event_types': {},
            'resource_types': {},
            'users': set(),
            'compartments_with_events': set()
        }
        
        print(f"Scanning {len(self.compartments)} compartments for audit events...")
        print(f"Using {self.max_workers_compartments} parallel workers...")
        
        tracker = ProgressTracker(len(self.compartments))
        completed = 0
        
        # Helper function for parallel processing
        def fetch_audit_events(comp_id):
            command = [
                'oci', 'audit', 'event', 'list',
                '--compartment-id', comp_id,
                '--start-time', f"{from_date}T00:00:00.000Z",
                '--end-time', f"{to_date}T23:59:59.999Z",
                '--all',
                '--output', 'json'
            ]
            
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    response = json.loads(result.stdout)
                    return comp_id, response.get('data', [])
                else:
                    return comp_id, []
            except Exception:
                return comp_id, []
        
        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers_compartments) as executor:
            future_to_compartment = {
                executor.submit(fetch_audit_events, comp_id): comp_id
                for comp_id in self.compartments
            }
            
            for future in as_completed(future_to_compartment):
                comp_id, events = future.result()
                completed += 1
                
                if events:
                    all_events.extend(events)
                    event_stats['compartments_with_events'].add(comp_id)
                    
                    # Analyze events
                    for event in events:
                        event_stats['total_events'] += 1
                        
                        event_type = event.get('data', {}).get('eventName', 'Unknown')
                        event_stats['event_types'][event_type] = event_stats['event_types'].get(event_type, 0) + 1
                        
                        resource_type = event.get('data', {}).get('resourceName', 'Unknown')
                        event_stats['resource_types'][resource_type] = event_stats['resource_types'].get(resource_type, 0) + 1
                        
                        principal = event.get('data', {}).get('identity', {}).get('principalName', '')
                        if principal:
                            event_stats['users'].add(principal)
                
                tracker.update(completed)
        
        tracker.finish()
        
        # Convert sets to lists for JSON serialization
        result = {
            'collection_period': {
                'from_date': from_date,
                'to_date': to_date
            },
            'total_events': event_stats['total_events'],
            'compartments_with_events': len(event_stats['compartments_with_events']),
            'unique_users': len(event_stats['users']),
            'event_types': dict(sorted(event_stats['event_types'].items(), key=lambda x: x[1], reverse=True)),
            'resource_types': dict(sorted(event_stats['resource_types'].items(), key=lambda x: x[1], reverse=True)),
            'sample_events': all_events[:1000]  # Store first 1000 events
        }
        
        print(f"✅ Collected {result['total_events']} audit events")
        print(f"  📊 Unique event types: {len(result['event_types'])}")
        print(f"  📊 Unique resource types: {len(result['resource_types'])}")
        print(f"  📊 Unique users: {result['unique_users']}")
        
        # Show top 5 event types
        print("\n📋 Top 5 event types:")
        for event_type, count in list(result['event_types'].items())[:5]:
            print(f"  🔹 {event_type}: {count}")
        
        return result
    
    def collect_event_rules(self):
        """
        Collect event rules from OCI Events service.
        Data Point: Event Rules
        API: oci.events.EventsClient.list_rules(compartment_id)
        Purpose: Understand automated actions and event-driven workflows
        
        Returns:
            Dictionary with event rules by compartment
        """
        print(f"\n{'='*70}")
        print("⚡ Collecting Event Rules")
        print(f"{'='*70}")
        
        if not self.compartments:
            self._get_all_compartments()
        
        all_rules = []
        rule_stats = {
            'total_rules': 0,
            'enabled_rules': 0,
            'disabled_rules': 0,
            'action_types': {},
            'compartments_with_rules': set()
        }
        
        print(f"Scanning {len(self.compartments)} compartments for event rules...")
        print(f"Using {self.max_workers_compartments} parallel workers...")
        
        tracker = ProgressTracker(len(self.compartments))
        completed = 0
        
        # Helper function for parallel processing
        def fetch_event_rules(comp_id):
            command = [
                'oci', 'events', 'rule', 'list',
                '--compartment-id', comp_id,
                '--all',
                '--output', 'json'
            ]
            
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    response = json.loads(result.stdout)
                    return comp_id, response.get('data', [])
                else:
                    return comp_id, []
            except Exception:
                return comp_id, []
        
        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers_compartments) as executor:
            future_to_compartment = {
                executor.submit(fetch_event_rules, comp_id): comp_id
                for comp_id in self.compartments
            }
            
            for future in as_completed(future_to_compartment):
                comp_id, rules = future.result()
                completed += 1
                
                if rules:
                    all_rules.extend(rules)
                    rule_stats['compartments_with_rules'].add(comp_id)
                    
                    # Analyze rules
                    for rule in rules:
                        rule_stats['total_rules'] += 1
                        
                        if rule.get('lifecycle-state') == 'ACTIVE':
                            rule_stats['enabled_rules'] += 1
                        else:
                            rule_stats['disabled_rules'] += 1
                        
                        # Analyze actions
                        actions = rule.get('actions', {})
                        if isinstance(actions, dict):
                            for action in actions.get('actions', []):
                                action_type = action.get('action-type', 'Unknown')
                                rule_stats['action_types'][action_type] = rule_stats['action_types'].get(action_type, 0) + 1
                
                tracker.update(completed)
        
        tracker.finish()
        
        result = {
            'total_rules': rule_stats['total_rules'],
            'enabled_rules': rule_stats['enabled_rules'],
            'disabled_rules': rule_stats['disabled_rules'],
            'compartments_with_rules': len(rule_stats['compartments_with_rules']),
            'action_types': dict(sorted(rule_stats['action_types'].items(), key=lambda x: x[1], reverse=True)),
            'rules': all_rules
        }
        
        print(f"✅ Collected {result['total_rules']} event rules")
        print(f"  📊 Enabled: {result['enabled_rules']}")
        print(f"  📊 Disabled: {result['disabled_rules']}")
        print(f"  📊 Compartments with rules: {result['compartments_with_rules']}")
        
        # Show action types
        if result['action_types']:
            print("\n📋 Action types:")
            for action_type, count in result['action_types'].items():
                print(f"  ⚡ {action_type}: {count}")
        
        return result
    
    def collect_all(self, from_date=None, to_date=None):
        """
        Collect all growth-related data including performance metrics, audit events, and event rules.
        
        Args:
            from_date: Start date for usage/cost queries (YYYY-MM-DD)
            to_date: End date for usage/cost queries (YYYY-MM-DD)
            
        Returns:
            Dictionary with all collected data
        """
        print("="*70)
        print("🚀 OCI Growth Collection - Comprehensive Analysis")
        print("="*70)
        print(f"Tenancy: {self.tenancy_ocid}")
        print(f"Region: {self.home_region}")
        if from_date and to_date:
            print(f"Date Range: {from_date} to {to_date}")
        
        results = {
            'collection_timestamp': datetime.now().isoformat(),
            'tenancy_ocid': self.tenancy_ocid,
            'home_region': self.home_region
        }
        
        # Collect tag structure data (no date range needed)
        results['compartments'] = self._get_all_compartments()
        results['tag_namespaces'] = self.collect_tag_namespaces()
        results['tag_definitions'] = self.collect_tag_definitions()
        results['tag_defaults'] = self.collect_tag_defaults()
        
        # Collect usage-based tag data (requires date range)
        if from_date and to_date:
            results['resource_tags'] = self.collect_resource_tags(from_date, to_date)
            results['cost_tracking_tags'] = self.collect_cost_tracking_tags(from_date, to_date)
            
            # Collect performance metrics
            results['performance_metrics'] = self.collect_performance_metrics(from_date, to_date)
            
            # Collect audit events
            results['audit_events'] = self.collect_audit_events(from_date, to_date)
        else:
            print("\n⚠️  Skipping date-range-dependent collections (no date range provided)")
        
        # Collect event rules (no date range needed)
        results['event_rules'] = self.collect_event_rules()
        
        # Save all collected data
        self._save_results(results)
        
        return results
    
    def _save_results(self, results):
        """Save collected data to JSON file."""
        output_file = self.output_dir / 'growth_collection_tags.json'
        
        print(f"\n{'='*70}")
        print("💾 Saving Growth Collection Results")
        print(f"{'='*70}")
        
        spinner = ProgressSpinner("Writing data to file...")
        spinner.start()
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        spinner.stop()
        
        print(f"✅ Growth collection data saved to {output_file}")
        
        # Generate summary report
        summary_file = self.output_dir / 'growth_collection_summary.txt'
        self._generate_summary_report(results, summary_file)
        
        print(f"✅ Summary report saved to {summary_file}")
    
    def _generate_summary_report(self, results, output_file):
        """Generate a human-readable summary report."""
        with open(output_file, 'w') as f:
            f.write("="*70 + "\n")
            f.write("OCI Growth Collection - Tag Analysis Summary\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Collection Timestamp: {results.get('collection_timestamp', 'N/A')}\n")
            f.write(f"Tenancy OCID: {results.get('tenancy_ocid', 'N/A')}\n")
            f.write(f"Home Region: {results.get('home_region', 'N/A')}\n\n")
            
            # Compartments
            f.write("-"*70 + "\n")
            f.write("COMPARTMENTS\n")
            f.write("-"*70 + "\n")
            comps = results.get('compartments', [])
            f.write(f"Total Compartments: {len(comps)}\n\n")
            
            # Tag Namespaces
            f.write("-"*70 + "\n")
            f.write("TAG NAMESPACES\n")
            f.write("-"*70 + "\n")
            namespaces = results.get('tag_namespaces', [])
            f.write(f"Total Tag Namespaces: {len(namespaces)}\n")
            for ns in namespaces:
                f.write(f"  - {ns.get('name', 'N/A')}: {ns.get('description', 'No description')}\n")
            f.write("\n")
            
            # Tag Definitions
            f.write("-"*70 + "\n")
            f.write("TAG DEFINITIONS\n")
            f.write("-"*70 + "\n")
            definitions = results.get('tag_definitions', {})
            total_tags = sum(len(ns_data.get('tags', [])) for ns_data in definitions.values())
            f.write(f"Total Tag Definitions: {total_tags}\n")
            for ns_id, ns_data in definitions.items():
                ns_name = ns_data.get('namespace_name', 'Unknown')
                tags = ns_data.get('tags', [])
                f.write(f"  Namespace '{ns_name}': {len(tags)} tags\n")
                for tag in tags[:5]:  # Show first 5
                    f.write(f"    - {tag.get('name', 'N/A')}\n")
                if len(tags) > 5:
                    f.write(f"    ... and {len(tags) - 5} more\n")
            f.write("\n")
            
            # Tag Defaults
            f.write("-"*70 + "\n")
            f.write("TAG DEFAULTS (Auto-tagging Rules)\n")
            f.write("-"*70 + "\n")
            defaults = results.get('tag_defaults', [])
            f.write(f"Total Tag Defaults: {len(defaults)}\n")
            for td in defaults[:10]:  # Show first 10
                f.write(f"  - {td.get('tag-definition-name', 'N/A')} = {td.get('value', 'N/A')}\n")
            if len(defaults) > 10:
                f.write(f"  ... and {len(defaults) - 10} more\n")
            f.write("\n")
            
            # Resource Tags (if available)
            if 'resource_tags' in results and results['resource_tags']:
                f.write("-"*70 + "\n")
                f.write("RESOURCE TAGS\n")
                f.write("-"*70 + "\n")
                rt = results['resource_tags']
                f.write(f"Total Records: {rt.get('total_records', 0)}\n")
                f.write(f"Unique Tag Namespaces: {len(rt.get('unique_tag_namespaces', []))}\n")
                f.write(f"Unique Tag Keys: {len(rt.get('unique_tag_keys', []))}\n")
                f.write(f"Resources with Tags: {rt.get('resources_with_tags_count', 0)}\n\n")
            
            # Cost-Tracking Tags (if available)
            if 'cost_tracking_tags' in results and results['cost_tracking_tags']:
                f.write("-"*70 + "\n")
                f.write("COST-TRACKING TAGS\n")
                f.write("-"*70 + "\n")
                ct = results['cost_tracking_tags']
                f.write(f"Total Cost Tracked: ${ct.get('total_cost', 0):,.2f}\n")
                f.write(f"Unique Tag Combinations: {ct.get('unique_tag_combinations', 0)}\n")
                f.write("\nTop 10 Cost-Driving Tags:\n")
                cost_by_tag = ct.get('cost_by_tag', {})
                for i, (tag_full, tag_data) in enumerate(list(cost_by_tag.items())[:10], 1):
                    f.write(f"  {i}. {tag_full}: ${tag_data['total_cost']:,.2f}\n")
                f.write("\n")
            
            # Performance Metrics (if available)
            if 'performance_metrics' in results and results['performance_metrics']:
                f.write("-"*70 + "\n")
                f.write("PERFORMANCE METRICS\n")
                f.write("-"*70 + "\n")
                pm = results['performance_metrics']
                period = pm.get('collection_period', {})
                f.write(f"Collection Period: {period.get('from_date', 'N/A')} to {period.get('to_date', 'N/A')}\n\n")
                
                metrics_by_ns = pm.get('metrics_by_namespace', {})
                for namespace, ns_data in metrics_by_ns.items():
                    f.write(f"{ns_data.get('display_name', namespace)}:\n")
                    for metric_name, metric_data in ns_data.get('metrics', {}).items():
                        data_points = metric_data.get('data_points', 0)
                        f.write(f"  - {metric_name}: {data_points} data points\n")
                    f.write("\n")
            
            # Audit Events (if available)
            if 'audit_events' in results and results['audit_events']:
                f.write("-"*70 + "\n")
                f.write("AUDIT EVENTS\n")
                f.write("-"*70 + "\n")
                ae = results['audit_events']
                period = ae.get('collection_period', {})
                f.write(f"Collection Period: {period.get('from_date', 'N/A')} to {period.get('to_date', 'N/A')}\n")
                f.write(f"Total Events: {ae.get('total_events', 0)}\n")
                f.write(f"Unique Users: {ae.get('unique_users', 0)}\n")
                f.write(f"Compartments with Events: {ae.get('compartments_with_events', 0)}\n")
                
                f.write("\nTop 10 Event Types:\n")
                event_types = ae.get('event_types', {})
                for i, (event_type, count) in enumerate(list(event_types.items())[:10], 1):
                    f.write(f"  {i}. {event_type}: {count}\n")
                
                f.write("\nTop 10 Resource Types:\n")
                resource_types = ae.get('resource_types', {})
                for i, (resource_type, count) in enumerate(list(resource_types.items())[:10], 1):
                    f.write(f"  {i}. {resource_type}: {count}\n")
                f.write("\n")
            
            # Event Rules (if available)
            if 'event_rules' in results and results['event_rules']:
                f.write("-"*70 + "\n")
                f.write("EVENT RULES\n")
                f.write("-"*70 + "\n")
                er = results['event_rules']
                f.write(f"Total Rules: {er.get('total_rules', 0)}\n")
                f.write(f"Enabled Rules: {er.get('enabled_rules', 0)}\n")
                f.write(f"Disabled Rules: {er.get('disabled_rules', 0)}\n")
                f.write(f"Compartments with Rules: {er.get('compartments_with_rules', 0)}\n")
                
                action_types = er.get('action_types', {})
                if action_types:
                    f.write("\nAction Types:\n")
                    for action_type, count in action_types.items():
                        f.write(f"  - {action_type}: {count}\n")
                f.write("\n")
            
            f.write("="*70 + "\n")
            f.write("End of Report\n")
            f.write("="*70 + "\n")
