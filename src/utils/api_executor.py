"""
API execution utilities for concurrent OCI API calls.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import json
import subprocess
import sys
from pathlib import Path
from .progress import ProgressSpinner


class OCIAPIExecutor:
    """Execute OCI API calls with progress tracking."""
    
    def __init__(self, tenancy_ocid, home_region, output_dir='output'):
        """Initialize API executor."""
        self.tenancy_ocid = tenancy_ocid
        self.home_region = home_region
        self.api_endpoint = f"https://usageapi.{home_region}.oci.oraclecloud.com/20200107/usage"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def make_api_call(self, query_type, group_by_fields, call_name, from_date, to_date):
        """
        Make a single API call to OCI Usage API with progress tracking.
        
        Args:
            query_type: Type of query (COST or USAGE)
            group_by_fields: List of fields to group by
            call_name: Name of the API call for logging
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            API response data or None if failed
        """
        # Build request body
        request_body = {
            "tenantId": self.tenancy_ocid,
            "timeUsageStarted": f"{from_date}T00:00:00Z",
            "timeUsageEnded": f"{to_date}T00:00:00Z",
            "granularity": "DAILY",
            "queryType": query_type,
            "groupBy": group_by_fields,
            "compartmentDepth": 4
        }
        
        # Save request body to temp file
        request_file = self.output_dir / Path(f"request_{call_name}.json")
        with open(request_file, 'w') as f:
            json.dump(request_body, f, indent=2)
        
        # Create and start progress spinner
        spinner = ProgressSpinner(f"🌐 Contacting OCI API for {call_name}...")
        spinner.start()
        
        result = None
        try:
            # Execute OCI CLI raw-request
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
            
            # Stop spinner
            spinner.stop()
            
            # Clean up temp file
            request_file.unlink()
            
            if result.returncode != 0:
                print(f"❌ API call failed: {result.stderr}")
                print(f"\n📋 Debug information:")
                print(f"   Return code: {result.returncode}")
                print(f"   Command: oci raw-request")
                print(f"   Stderr: {result.stderr[:300]}")
                return None
            
            # Parse response
            response = json.loads(result.stdout)
            
            # Check for API errors
            if 'code' in response and 'message' in response:
                print(f"❌ API Error: {response.get('message')}")
                print(f"\n📋 Error details for debugging:")
                print(f"   Error code: {response.get('code')}")
                print(f"   Error message: {response.get('message')}")
                if 'details' in response:
                    print(f"   Details: {response.get('details')}")
                return None
            
            # Extract data
            api_data = response.get('data', response)
            
            if isinstance(api_data, dict) and 'items' in api_data:
                print(f"✅ Success: Retrieved {len(api_data['items'])} records")
                return api_data
            
            print("❌ Unexpected API response format")
            print(f"\n📋 Response details for debugging:")
            print(f"   Response type: {type(api_data)}")
            print(f"   Response keys: {list(api_data.keys()) if isinstance(api_data, dict) else 'N/A'}")
            print(f"   Full response (first 500 chars): {str(response)[:500]}")
            
            # Save full response for investigation
            debug_file = self.output_dir / Path(f"debug_response_{call_name}.json")
            with open(debug_file, 'w') as f:
                json.dump(response, f, indent=2)
            print(f"   📁 Full response saved to: {debug_file}")
            
            return None
        
        except subprocess.TimeoutExpired:
            spinner.stop()
            print("❌ API call timeout after 300 seconds")
            print("\n📋 Debug information:")
            print("   The API took longer than 300 seconds to respond")
            print("   This may indicate a large dataset or network issues")
            return None
        except json.JSONDecodeError as json_err:
            spinner.stop()
            print(f"❌ Failed to parse API response as JSON: {json_err}")
            print("\n📋 Debug information:")
            if result:
                print(f"   Raw response (first 500 chars): {result.stdout[:500]}")
            return None
        except Exception as e:
            spinner.stop()
            print(f"❌ API call failed: {e}")
            print("\n📋 Debug information:")
            print(f"   Exception type: {type(e).__name__}")
            print(f"   Exception message: {str(e)}")
            return None
    
    def make_parallel_calls(self, calls):
        """
        Execute multiple API calls in sequence with clear separation.
        
        Args:
            calls: List of tuples (query_type, group_by_fields, call_name, from_date, to_date)
        
        Returns:
            List of API responses in the same order as input
        """
        results = []
        
        for query_type, group_by_fields, call_name, from_date, to_date in calls:
            print(f"\n{'='*70}")
            print(f"🔄 Making {call_name}")
            print(f"{'='*70}")
            
            result = self.make_api_call(
                query_type=query_type,
                group_by_fields=group_by_fields,
                call_name=call_name,
                from_date=from_date,
                to_date=to_date
            )
            
            results.append(result)
        
        return results
