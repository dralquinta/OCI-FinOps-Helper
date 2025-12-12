"""
Oracle Cloud Advisor Recommendations fetcher.
Fetches cost-saving recommendations from the Cloud Advisor API using REST API.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
from .progress import ProgressSpinner


class OCIRecommendationsFetcher:
    """Fetch cost-saving recommendations from Oracle Cloud Advisor API using REST API."""
    
    def __init__(self, tenancy_ocid, region, output_dir='output', currency='USD'):
        """
        Initialize recommendations fetcher.
        
        Args:
            tenancy_ocid: OCI Tenancy OCID
            region: OCI Region
            output_dir: Output directory for recommendations
            currency: Target currency for cost display (default: USD)
        """
        self.tenancy_ocid = tenancy_ocid
        self.region = region
        self.currency = currency  # Default is USD
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_endpoint = f"https://optimizer.{region}.oraclecloud.com/20200606/recommendations"
    
    def fetch_recommendations_api(self):
        """
        Fetch recommendations using OCI CLI (optimizer recommendation-summary list).
        Note: Using CLI command as a reliable API wrapper.
        
        Returns:
            dict: Recommendations data or None if failed
        """
        print(f"\n{'='*70}")
        print("💡 Fetching Cost-Saving Recommendations")
        print(f"{'='*70}")
        print(f"API Endpoint: {self.api_endpoint}")
        print(f"Tenancy: {self.tenancy_ocid}")
        print(f"Currency: {self.currency}")
        
        spinner = ProgressSpinner("🌐 Contacting Oracle Cloud Advisor...")
        spinner.start()
        
        try:
            # Execute OCI CLI command (reliable API access method)
            result = subprocess.run(
                [
                    'oci', 'optimizer', 'recommendation-summary', 'list',
                    '--compartment-id', self.tenancy_ocid,
                    '--compartment-id-in-subtree', 'true',
                    '--region', self.region,
                    '--all',
                    '--output', 'json'
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            spinner.stop()
            
            if result.returncode != 0:
                # Check if it's an authorization error
                is_auth_error = 'NotAuthorizedOrNotFound' in result.stderr or 'Authorization failed' in result.stderr
                
                print(f"❌ API call failed: {result.stderr[:50]}...")
                print("\n📋 Debug information:")
                print(f"   Return code: {result.returncode}")
                print(f"   Region: {self.region}")
                print(f"   Tenancy: {self.tenancy_ocid[:50]}...")
                
                if is_auth_error:
                    print("\n💡 Troubleshooting steps:")
                    print("   1. Verify IAM policy grants access to Cloud Advisor:")
                    print("      allow group <YourGroup> to read cloud-advisor-family in tenancy")
                    print("   2. Confirm the region is subscribed and Cloud Advisor is available")
                    print("   3. Check that you have proper permissions in the tenancy")
                    print("   4. Verify your OCI CLI session is authenticated:")
                    print("      oci session validate --auth security_token")
                    print("\n   Required IAM Policy:")
                    print("   allow group <YourGroup> to read cloud-advisor-family in tenancy")
                    print("   allow group <YourGroup> to manage optimizer-api-family in tenancy")
                
                print(f"\n   Full error output (first 500 chars):")
                print(f"   {result.stderr[:500]}")
                return None
            
            # Parse response
            response = json.loads(result.stdout)
            
            # Check for API errors
            if 'code' in response and 'message' in response:
                print(f"❌ API Error: {response.get('message')}")
                print("\n📋 Error details:")
                print(f"   Error code: {response.get('code')}")
                return None
            
            # Extract recommendations
            api_data = response.get('data', response)
            
            if isinstance(api_data, dict) and 'items' in api_data:
                items = api_data['items']
                print(f"✅ Success: Retrieved {len(items)} recommendations")
                return api_data
            
            if isinstance(api_data, list):
                print(f"✅ Success: Retrieved {len(api_data)} recommendations (list format)")
                return {"items": api_data}
            
            print("❌ Unexpected API response format")
            return None
        
        except subprocess.TimeoutExpired:
            spinner.stop()
            print("❌ API call timeout after 300 seconds")
            return None
        
        except json.JSONDecodeError as json_err:
            spinner.stop()
            print(f"❌ Failed to parse API response: {json_err}")
            return None
        
        except Exception as e:
            spinner.stop()
            print(f"❌ Failed to fetch recommendations: {e}")
            return None
    
    def generate_category_summary(self, items):
        """Generate summary by category with actionable insights."""
        categories = {}
        
        for item in items:
            category_name = item.get('name', 'unknown')
            importance = item.get('importance', 'UNKNOWN')
            savings = float(item.get('estimated-cost-saving', 0))
            state = item.get('lifecycle-state', 'UNKNOWN')
            resource_counts = item.get('resource-counts', [])
            
            # Count affected resources
            pending = sum(r.get('count', 0) for r in resource_counts if r.get('status') == 'PENDING')
            
            if category_name not in categories:
                categories[category_name] = {
                    'name': category_name,
                    'description': item.get('description', ''),
                    'importance': importance,
                    'total_savings': 0,
                    'affected_resources': 0,
                    'state': state,
                    'recommendation_id': item.get('id', '')
                }
            
            categories[category_name]['total_savings'] += savings
            categories[category_name]['affected_resources'] += pending
        
        return categories
    
    def format_actionable_report(self, recommendations_data):
        """
        Format recommendations into actionable steps.
        
        Args:
            recommendations_data: Raw recommendations data
        
        Returns:
            str: Formatted actionable report
        """
        items = recommendations_data.get('items', [])
        
        if not items:
            return "No recommendations available at this time.\n"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("ORACLE CLOUD ADVISOR - COST OPTIMIZATION RECOMMENDATIONS")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Tenancy: {self.tenancy_ocid}")
        report_lines.append(f"Region: {self.region}")
        report_lines.append("")
        
        # Calculate aggregated summary
        total_savings = sum(float(item.get('estimated-cost-saving', 0)) for item in items)
        active_count = sum(1 for item in items if item.get('lifecycle-state') == 'ACTIVE')
        critical_count = sum(1 for item in items if item.get('importance') == 'CRITICAL')
        high_count = sum(1 for item in items if item.get('importance') == 'HIGH')
        
        # Always use the configured currency (default: USD)
        currency = self.currency
        
        # EXECUTIVE SUMMARY
        report_lines.append("━" * 80)
        report_lines.append("EXECUTIVE SUMMARY")
        report_lines.append("━" * 80)
        report_lines.append(f"Total Recommendations:       {len(items)}")
        report_lines.append(f"Active Recommendations:      {active_count}")
        report_lines.append(f"Critical Priority:           {critical_count}")
        report_lines.append(f"High Priority:               {high_count}")
        report_lines.append(f"Estimated Monthly Savings:   {total_savings:,.2f} {currency}")
        report_lines.append("")
        
        # CATEGORY BREAKDOWN
        categories = self.generate_category_summary(items)
        
        report_lines.append("━" * 80)
        report_lines.append("SAVINGS BY CATEGORY")
        report_lines.append("━" * 80)
        
        # Sort categories by savings
        sorted_categories = sorted(categories.values(), 
                                   key=lambda x: x['total_savings'], 
                                   reverse=True)
        
        for idx, cat in enumerate(sorted_categories, 1):
            # Get human-readable category name
            category_name = self._get_category_display_name(cat['name'])
            report_lines.append(f"\n{idx}. {category_name}")
            report_lines.append(f"   Priority:           {cat['importance']}")
            report_lines.append(f"   Potential Savings:  {cat['total_savings']:,.2f} {currency}")
            report_lines.append(f"   Affected Resources: {cat['affected_resources']}")
            report_lines.append(f"   Status:             {cat['state']}")
        
        report_lines.append("")
        
        # DETAILED ACTIONABLE STEPS
        report_lines.append("━" * 80)
        report_lines.append("ACTIONABLE RECOMMENDATIONS (PRIORITIZED)")
        report_lines.append("━" * 80)
        report_lines.append("")
        
        # Sort by importance and savings
        importance_order = {'CRITICAL': 0, 'HIGH': 1, 'MODERATE': 2, 'LOW': 3, 'MINOR': 4}
        sorted_items = sorted(
            items,
            key=lambda x: (
                importance_order.get(x.get('importance', 'MINOR'), 99),
                -float(x.get('estimated-cost-saving', 0))
            )
        )
        
        for idx, item in enumerate(sorted_items, 1):
            savings = float(item.get('estimated-cost-saving', 0))
            importance = item.get('importance', 'UNKNOWN')
            name = item.get('name', 'Unknown')
            description = item.get('description', 'No description available')
            rec_id = item.get('id', '')
            state = item.get('lifecycle-state', 'UNKNOWN')
            
            # Get resource counts
            resource_counts = item.get('resource-counts', [])
            pending = sum(r.get('count', 0) for r in resource_counts if r.get('status') == 'PENDING')
            
            report_lines.append(f"[{idx}] {name.upper()}")
            report_lines.append(f"{'─' * 80}")
            report_lines.append(f"Priority:        {importance}")
            report_lines.append(f"Savings:         {savings:,.2f} {currency}/month")
            report_lines.append(f"Status:          {state}")
            report_lines.append(f"Resources:       {pending} resource(s) affected")
            report_lines.append(f"Description:     {description}")
            report_lines.append(f"Recommendation:  {rec_id}")
            report_lines.append("")
            
            # Generate specific actions based on recommendation name
            explanation, actions, cli_command = self._generate_actions(name, rec_id, pending)
            
            report_lines.append("WHAT THIS MEANS:")
            report_lines.append(f"  {explanation}")
            report_lines.append("")
            report_lines.append("ACTIONS TO TAKE:")
            for action_idx, action in enumerate(actions, 1):
                report_lines.append(f"  {action_idx}. {action}")
            report_lines.append("")
            report_lines.append("CLI COMMAND TO EXECUTE:")
            report_lines.append(f"  {cli_command}")
            
            report_lines.append("")
        
        # FOOTER
        report_lines.append("━" * 80)
        report_lines.append("HOW TO IMPLEMENT RECOMMENDATIONS")
        report_lines.append("━" * 80)
        report_lines.append("")
        report_lines.append("Via OCI Console:")
        report_lines.append("  1. Navigate to: Governance & Administration > Cloud Advisor")
        report_lines.append("  2. Select the recommendation category")
        report_lines.append("  3. Review resources and apply recommendations")
        report_lines.append("")
        report_lines.append("Via OCI CLI:")
        report_lines.append("  # View recommendation details")
        report_lines.append("  oci optimizer recommendation get --recommendation-id <RECOMMENDATION_ID>")
        report_lines.append("")
        report_lines.append("  # Apply recommendation")
        report_lines.append("  oci optimizer recommendation bulk-apply \\")
        report_lines.append("    --recommendation-id <RECOMMENDATION_ID> \\")
        report_lines.append("    --status IMPLEMENTED")
        report_lines.append("")
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def _get_category_display_name(self, category_code):
        """
        Convert category code to human-readable name.
        
        Args:
            category_code: Technical category code from API
            
        Returns:
            str: Human-readable category name with description
        """
        category_map = {
            'cost-management-boot-volume-attachment-name': 'Boot Volumes - Optimize size and performance settings',
            'cost-management-block-volume-attachment-name': 'Block Volumes - Remove unattached or underutilized volumes',
            'create-ccd-commitment': 'Compute Commitments - Purchase 1-3 year commitments for discounts',
            'cost-management-compute-host-burstable-name': 'Compute Instances - Switch to burstable shapes for variable workloads',
            'cost-management-compute-host-terminated-name': 'Terminated Instances - Clean up resources from stopped instances',
            'cost-management-compute-host-underutilized-name': 'Underutilized Instances - Right-size based on actual usage',
            'cost-management-load-balancer-underutilized-name': 'Load Balancers - Consolidate or remove low-traffic load balancers',
            'cost-management-autonomous-database-underutilized-name': 'Autonomous Databases - Reduce OCPUs or enable auto-scaling',
            'cost-management-object-storage-enable-olm-name': 'Object Storage - Enable lifecycle policies to archive old data',
            'high-availability-object-storage-enable-replication': 'Object Storage - Enable cross-region replication for DR',
            'high-availability-object-storage-enable-object-versioning': 'Object Storage - Enable versioning for data protection',
            'rightsize-exacs-x6-x7-x8-db-cluster': 'Exadata Cloud - Right-size database cluster resources',
            'rightsize-vmdb-system': 'VM Database - Right-size database system resources',
            'enable-db-management': 'Database Management - Enable monitoring and performance insights',
            'downsize-exacs-x6-x7-x8-db-cluster': 'Exadata Cloud - Downsize overprovisioned clusters',
            'downsize-vmdb-system': 'VM Database - Downsize overprovisioned systems',
            'performance-compute-host-highutilization-name': 'High CPU Instances - Upgrade instances with performance issues',
            'performance-load-balancer-highutilization-name': 'High Traffic Load Balancers - Increase bandwidth capacity',
            'high-availability-compute-fault-domain-name': 'Compute HA - Distribute instances across fault domains',
            'performance-boot-volume-enable-auto-tuning-name': 'Boot Volumes - Enable auto-tuning for optimal performance',
            'performance-block-volume-enable-auto-tuning-name': 'Block Volumes - Enable auto-tuning for optimal performance',
            'cost-management-compute-enable-monitoring-name': 'Compute Monitoring - Enable enhanced monitoring for optimization',
        }
        
        # Return mapped name or a cleaned version of the code
        return category_map.get(category_code.lower(), 
                               category_code.replace('-', ' ').replace('_', ' ').title())
    
    def _generate_actions(self, recommendation_name, rec_id, resource_count):
        """
        Generate specific actions based on recommendation type.
        
        Returns:
            tuple: (explanation, actions_list, cli_command)
        """
        actions = []
        explanation = ""
        cli_command = ""
        rec_lower = recommendation_name.lower()
        
        # Generate detailed explanations and actions based on recommendation name
        if 'boot-volume-attachment' in rec_lower:
            explanation = "Your compute instances are oversized based on CPU, memory, and network utilization metrics. Right-sizing can reduce costs by up to 50% while maintaining performance."
            actions.append(f"Review {resource_count} instance(s) for downsizing opportunities")
            actions.append("Analyze CPU, memory, and network utilization metrics")
            actions.append("Resize to smaller shape via OCI Console or CLI")
            actions.append("Schedule during maintenance window to minimize disruption")
            cli_command = f"oci compute instance update --instance-id <instance-ocid> --shape <new-shape> --region {self.region}"
        
        elif 'block-volume-attachment' in rec_lower:
            explanation = f"You have {resource_count} block volumes that are either unattached, underutilized, or using excess performance capacity. These volumes continue to incur storage costs even when not actively used."
            actions.append(f"Identify the {resource_count} block volumes with optimization opportunities")
            actions.append("List unattached volumes: these can be deleted if data is no longer needed")
            actions.append("Review volumes with low I/O usage - consider reducing VPUs per GB")
            actions.append("Delete unattached volumes or downgrade performance tier to save costs")
            cli_command = f"oci bv volume list --compartment-id {self.tenancy_ocid} --lifecycle-state AVAILABLE --region {self.region}"
        
        elif 'ccd' in rec_lower or 'commitment' in rec_lower:
            explanation = f"Based on your consistent usage patterns across {resource_count} resource(s), you can save significantly by purchasing Compute Cloud Credits (CCD) commitments. Commitments offer 33-52% discounts for 1-year terms or 46-60% for 3-year terms."
            actions.append(f"Analyze historical usage for the {resource_count} eligible resource(s)")
            actions.append("Calculate your average monthly compute spend over the last 3-6 months")
            actions.append("Purchase CCD commitment matching your baseline usage (1-year or 3-year term)")
            actions.append("Continue using pay-as-you-go for variable/burst workloads above commitment level")
            cli_command = f"oci optimizer recommendation get --recommendation-id {rec_id} --region {self.region} --output json"
        
        elif 'compute-host-terminated' in rec_lower:
            explanation = f"You have {resource_count} compute instance(s) in TERMINATED or STOPPED state that still have associated resources (boot volumes, reserved IPs) incurring costs. Fully removing these instances can eliminate ongoing charges."
            actions.append(f"List the {resource_count} terminated/stopped instance(s)")
            actions.append("Verify these instances are no longer needed")
            actions.append("Delete associated boot volumes (they continue billing even after instance termination)")
            actions.append("Release any reserved public IPs attached to terminated instances")
            cli_command = f"oci compute instance list --compartment-id {self.tenancy_ocid} --lifecycle-state TERMINATED --region {self.region}"
        
        elif 'compute-host-underutilized' in rec_lower or 'compute-host-burstable' in rec_lower:
            explanation = f"You have {resource_count} compute instance(s) with consistently low CPU, memory, or network utilization. Right-sizing these instances to smaller shapes can reduce costs by 30-70% while still meeting workload requirements."
            actions.append(f"Review utilization metrics for the {resource_count} underutilized instance(s)")
            actions.append("Check CPU average over last 30 days - if consistently below 20%, consider smaller shape")
            actions.append("Evaluate memory usage - downsize if actual usage is <50% of allocated")
            actions.append("Resize instances during maintenance window, test performance after change")
            cli_command = f"oci compute instance action --instance-id <instance-ocid> --action SOFTSTOP && oci compute instance update --instance-id <instance-ocid> --shape <smaller-shape> --region {self.region}"
        
        elif 'load-balancer-underutilized' in rec_lower:
            explanation = f"You have {resource_count} load balancer(s) with low traffic or connection counts. Load balancers have fixed hourly costs regardless of usage - consolidating or removing underutilized load balancers can significantly reduce costs."
            actions.append(f"Review traffic patterns for the {resource_count} load balancer(s)")
            actions.append("Check average bandwidth usage and connection counts over the last 30 days")
            actions.append("Consolidate multiple low-traffic load balancers where possible")
            actions.append("Delete load balancers with negligible traffic and use alternative routing")
            cli_command = f"oci lb load-balancer list --compartment-id {self.tenancy_ocid} --region {self.region}"
        
        elif 'autonomous-database-underutilized' in rec_lower:
            explanation = f"You have {resource_count} Autonomous Database instance(s) with low CPU utilization. ADB charges per OCPU hour - reducing OCPU count or switching to auto-scaling can optimize costs while maintaining performance."
            actions.append(f"Review CPU utilization for the {resource_count} ADB instance(s)")
            actions.append("If average CPU is consistently below 30%, reduce OCPU count")
            actions.append("Enable auto-scaling to handle peak loads without over-provisioning")
            actions.append("Consider stopping non-production databases during off-hours")
            cli_command = f"oci db autonomous-database update --autonomous-database-id <adb-ocid> --cpu-core-count <new-count> --region {self.region}"
        
        elif 'object-storage-enable-olm' in rec_lower:
            explanation = f"You have {resource_count} objects in Object Storage that could benefit from Object Lifecycle Management (OLM) policies. OLM automatically moves older objects to lower-cost Archive storage, reducing costs by up to 90% for infrequently accessed data."
            actions.append(f"Review the {resource_count} objects eligible for lifecycle management")
            actions.append("Identify objects not accessed in the last 90+ days")
            actions.append("Create OLM policy to auto-archive objects after specified age (e.g., 90 days)")
            actions.append("Configure auto-deletion for temporary/log objects after retention period")
            cli_command = f"oci os object-lifecycle-policy put --bucket-name <bucket-name> --namespace-name <namespace> --items file://lifecycle-policy.json --region {self.region}"
        
        elif 'enable-db-management' in rec_lower:
            explanation = f"Enabling Database Management on {resource_count} database(s) provides performance monitoring, tuning recommendations, and operational insights at no additional cost. This helps optimize database performance and identify cost-saving opportunities."
            actions.append(f"Enable Database Management for the {resource_count} database(s)")
            actions.append("Configure database management features: Performance Hub, SQL Monitoring")
            actions.append("Review automated tuning recommendations weekly")
            actions.append("Use insights to rightsize database resources")
            cli_command = f"oci database-management enable-external-database --external-database-id <db-ocid> --region {self.region}"
        
        elif 'object-storage-enable-object-versioning' in rec_lower:
            explanation = f"Enabling Object Storage versioning on {resource_count} buckets protects against accidental deletions and overwrites. While it adds minimal cost for version storage, it provides essential data protection and audit trail capabilities."
            actions.append(f"Enable versioning on the {resource_count} bucket(s)")
            actions.append("Configure lifecycle policies to automatically delete old versions after retention period")
            actions.append("Set appropriate retention based on compliance requirements (30-365 days)")
            actions.append("Monitor versioning storage costs and adjust retention as needed")
            cli_command = f"oci os bucket update --bucket-name <bucket-name> --namespace-name <namespace> --versioning Enabled --region {self.region}"
        
        elif 'object-storage-enable-replication' in rec_lower:
            explanation = f"Enabling cross-region replication for {resource_count} critical buckets provides disaster recovery and high availability. While replication adds storage and data transfer costs, it ensures business continuity for mission-critical data."
            actions.append(f"Configure replication for the {resource_count} critical bucket(s)")
            actions.append("Select target region based on geographic requirements and disaster recovery plan")
            actions.append("Set up replication policy for full bucket or prefix-based replication")
            actions.append("Monitor replication lag and costs - only replicate truly critical data")
            cli_command = f"oci os replication create-replication-policy --bucket-name <bucket-name> --namespace-name <namespace> --destination-bucket <dest-bucket> --destination-region <dest-region> --region {self.region}"
        
        elif 'rightsize-exacs' in rec_lower or 'rightsize-vmdb' in rec_lower or 'downsize-exacs' in rec_lower or 'downsize-vmdb' in rec_lower:
            explanation = f"Your database system(s) have {resource_count} instances that can be right-sized based on actual CPU, memory, and storage utilization. Database right-sizing can reduce costs by 20-60% while maintaining performance."
            actions.append(f"Review resource utilization for the {resource_count} database system(s)")
            actions.append("Analyze CPU, memory, and I/O metrics over last 30 days")
            actions.append("Downsize to appropriate shape or reduce enabled cores")
            actions.append("Schedule change during maintenance window, monitor performance after")
            cli_command = f"oci db system update --db-system-id <db-system-ocid> --cpu-core-count <new-count> --region {self.region}"
        
        elif 'compute-fault-domain' in rec_lower:
            explanation = f"You have {resource_count} compute instances not configured with fault domains. Distributing instances across fault domains improves high availability by isolating failures within the data center at no additional cost."
            actions.append(f"Review placement of the {resource_count} instance(s)")
            actions.append("Identify instances in the same fault domain that should be distributed")
            actions.append("Create new instances in different fault domains for redundancy")
            actions.append("Update deployment automation to specify fault domain placement")
            cli_command = f"oci compute instance launch --fault-domain FAULT-DOMAIN-1 --shape <shape> --compartment-id <compartment-ocid> --region {self.region}"
        
        elif 'enable-auto-tuning' in rec_lower:
            explanation = f"You have {resource_count} block/boot volumes that could benefit from auto-tuning. Auto-tuning automatically adjusts volume performance based on workload patterns at no extra cost, ensuring optimal performance."
            actions.append(f"Enable auto-tuning for the {resource_count} volume(s)")
            actions.append("Auto-tuning optimizes VPUs per GB automatically based on I/O patterns")
            actions.append("No manual VPU adjustments needed - system handles optimization")
            actions.append("Monitor volume performance after enabling to verify improvements")
            cli_command = f"oci bv volume update --volume-id <volume-ocid> --is-auto-tune-enabled true --region {self.region}"
        
        elif 'load-balancer-highutilization' in rec_lower:
            explanation = f"You have {resource_count} load balancer(s) experiencing high utilization. Upgrading bandwidth or adding additional load balancers prevents performance degradation and ensures application availability during traffic peaks."
            actions.append(f"Review traffic patterns for the {resource_count} load balancer(s)")
            actions.append("Check if bandwidth limits are being reached during peak hours")
            actions.append("Upgrade to higher bandwidth tier or add additional load balancers")
            actions.append("Implement horizontal scaling with multiple load balancers for high-traffic apps")
            cli_command = f"oci lb load-balancer update --load-balancer-id <lb-ocid> --shape-name <larger-shape> --region {self.region}"
        
        elif 'compute-host-highutilization' in rec_lower:
            explanation = f"You have {resource_count} compute instance(s) with consistently high CPU/memory utilization. Upgrading to larger shapes prevents performance issues and improves application responsiveness."
            actions.append(f"Review utilization metrics for the {resource_count} instance(s)")
            actions.append("Check if CPU consistently exceeds 80% or memory is fully utilized")
            actions.append("Upsize to larger shape with more OCPUs/memory")
            actions.append("Consider enabling auto-scaling for variable workloads")
            cli_command = f"oci compute instance update --instance-id <instance-ocid> --shape <larger-shape> --region {self.region}"
        
        elif 'enable-monitoring' in rec_lower:
            explanation = f"You have {resource_count} compute instances without enhanced monitoring enabled. Basic monitoring is free, but enhanced monitoring (1-minute intervals) provides critical insights for performance troubleshooting and cost optimization."
            actions.append(f"Enable enhanced monitoring for the {resource_count} instance(s)")
            actions.append("Configure 1-minute metric intervals for better visibility")
            actions.append("Set up alarms for CPU, memory, and disk utilization thresholds")
            actions.append("Use monitoring data to identify right-sizing opportunities")
            cli_command = f"oci compute instance update --instance-id <instance-ocid> --metadata '{{\\\"user_data\\\":\\\"<enable-monitoring-script>\\\"}}' --region {self.region}"
        
        else:
            # Generic actions for unmatched recommendation types
            explanation = f"Oracle Cloud Advisor identified an optimization opportunity for {resource_count} resource(s). Review the recommendation details to understand the specific improvements suggested and potential cost savings."
            actions.append(f"Review the {resource_count} affected resource(s) in Cloud Advisor console")
            actions.append("Get detailed recommendation information including affected resources")
            actions.append("Evaluate the impact and feasibility of implementing the recommendation")
            actions.append("Implement changes and mark recommendation as IMPLEMENTED when complete")
            cli_command = f"oci optimizer recommendation get --recommendation-id {rec_id} --region {self.region} --output json"
        
        return explanation, actions, cli_command
    
    def save_recommendations(self, recommendations_data, format_type='actionable'):
        """
        Save recommendations to files.
        
        Args:
            recommendations_data: Recommendations data dictionary
            format_type: 'actionable' for human-readable, 'json' for raw data, 'both' for both
        
        Returns:
            dict: Paths to saved files
        """
        if not recommendations_data:
            return None
        
        saved_files = {}
        
        try:
            # Always save raw JSON for programmatic access
            json_file = self.output_dir / 'recommendations.json'
            with open(json_file, 'w') as f:
                json.dump(recommendations_data, f, indent=2)
            saved_files['json'] = json_file
            print(f"✅ Raw JSON saved to {json_file}")
            
            # Save actionable report
            if format_type in ['actionable', 'both']:
                actionable_report = self.format_actionable_report(recommendations_data)
                report_file = self.output_dir / 'recommendations.out'
                with open(report_file, 'w') as f:
                    f.write(actionable_report)
                saved_files['report'] = report_file
                print(f"✅ Actionable report saved to {report_file}")
            
            return saved_files
        
        except Exception as e:
            print(f"❌ Failed to save recommendations: {e}")
            return None
    
    def fetch_and_save(self):
        """
        Fetch recommendations and save to files.
        
        Returns:
            dict: Paths to saved files or None if failed
        """
        recommendations = self.fetch_recommendations_api()
        if recommendations:
            files = self.save_recommendations(recommendations, format_type='both')
            if files:
                # Print summary
                items = recommendations.get('items', [])
                if items:
                    total_savings = sum(float(item.get('estimated-cost-saving', 0)) for item in items)
                    # Always use configured currency (default: USD)
                    currency = self.currency
                    
                    print(f"\n💰 Total Potential Savings: {total_savings:,.2f} {currency}/month")
                    print(f"📊 Total Recommendations: {len(items)}")
                
                return files
        return None
