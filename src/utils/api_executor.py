"""
API execution utilities for concurrent OCI API calls.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import json
import subprocess
try:
    from ..distribution import run_oci
except ImportError:  # Direct src/collector.py execution
    from distribution import run_oci
import sys
from pathlib import Path
from urllib.parse import urlencode
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
            # Usage queries paginate even though raw-request has no --all option.
            command = [
                'oci', 'raw-request', '--http-method', 'POST',
                '--target-uri', self.api_endpoint,
                '--request-body', f'file://{request_file}',
                '--region', self.home_region, '--output', 'json'
            ]
            items = []
            seen_pages = set()
            first_data = None
            while True:
                result = run_oci(command, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    # Never pass incomplete costs to downstream savings reports.
                    print(f"❌ API page failed: {result.stderr[:300]}")
                    return None
                response = json.loads(result.stdout)
                page_data = response.get('data', response)
                if not isinstance(page_data, dict) or not isinstance(page_data.get('items'), list):
                    print("❌ Unexpected Usage API page format")
                    return None
                if first_data is None:
                    first_data = dict(page_data)
                items.extend(page_data['items'])
                headers = response.get('headers', {})
                next_page = next((value for key, value in headers.items()
                                  if key.lower() == 'opc-next-page'), None)
                if not next_page:
                    break
                if next_page in seen_pages:
                    print("❌ Usage API repeated its page token")
                    return None
                seen_pages.add(next_page)
                command[command.index('--target-uri') + 1] = (
                    self.api_endpoint + '?' + urlencode({'page': next_page})
                )
            first_data['items'] = items
            response = {'data': first_data}
            spinner.stop()

            if result.returncode != 0:
                print(f"❌ API call failed: {result.stderr}")
                print(f"\n📋 Debug information:")
                print(f"   Return code: {result.returncode}")
                print(f"   Command: oci raw-request")
                print(f"   Stderr: {result.stderr[:300]}")
                return None
            
            # Parse response
            # All pages were parsed above.
            # Extract data first
            api_data = response.get('data', response)
            
            # Check for API errors in the data section
            if isinstance(api_data, dict) and 'code' in api_data and 'message' in api_data:
                error_code = api_data.get('code')
                error_message = api_data.get('message')
                
                print(f"❌ API Error: {error_message}")
                print(f"\n📋 Error details:")
                print(f"   Error code: {error_code}")
                print(f"   Region: {self.home_region}")
                print(f"   Tenancy: {self.tenancy_ocid[:50]}...")
                
                # Provide specific guidance based on error code
                if error_code == 'NotAuthorizedOrNotFound':
                    print(f"\n💡 Troubleshooting steps:")
                    print(f"   1. Verify IAM policy grants access to cost and usage data:")
                    print(f"      allow group <YourGroup> to read usage-reports in tenancy")
                    print(f"      allow group <YourGroup> to read usage-budgets in tenancy")
                    print(f"   2. Confirm the tenancy OCID is correct")
                    print(f"   3. Check that the region '{self.home_region}' is subscribed")
                    print(f"   4. Ensure you're using the home region for the tenancy")
                    print(f"   5. Verify your OCI CLI session is authenticated:")
                    print(f"      oci iam region list --auth security_token")
                
                if 'details' in api_data:
                    print(f"   Additional details: {api_data.get('details')}")
                
                # Save error response for investigation
                debug_file = self.output_dir / Path(f"debug_error_{call_name}.json")
                with open(debug_file, 'w') as f:
                    json.dump(response, f, indent=2)
                print(f"\n   📁 Full error response saved to: {debug_file}")
                
                return None
            
            # Check for successful response with items
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
        finally:
            spinner.stop()
            request_file.unlink(missing_ok=True)
    
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
