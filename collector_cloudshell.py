# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl

import requests
import sys
import pandas as pd
import json
import os
from datetime import date
try:
    # Try OCI SDK auth first (for local development)
    from oci.config import from_file
    from oci.signer import Signer
    OCI_SDK_AVAILABLE = True
except ImportError:
    # Fallback for Cloud Shell environment
    OCI_SDK_AVAILABLE = False
    print("OCI SDK not available, will use Cloud Shell authentication")

# Check if running in Cloud Shell
def is_cloud_shell():
    return os.environ.get('OCI_CLI_CLOUD_SHELL', '').lower() == 'true' or os.path.exists('/etc/oci_env')

def get_auth_method():
    """Determine the best authentication method for the current environment"""
    if is_cloud_shell():
        return "cloud_shell"
    elif OCI_SDK_AVAILABLE:
        return "oci_sdk"
    else:
        return "manual"

def get_cloud_shell_auth():
    """Get authentication headers for Cloud Shell using instance principal"""
    try:
        # In Cloud Shell, we can use the metadata service to get auth token
        import subprocess
        result = subprocess.run(['oci', 'iam', 'region', 'list', '--output', 'json'], 
                              capture_output=True, text=True, check=True)
        # If this works, OCI CLI is properly configured
        
        # Get auth token using OCI CLI
        token_result = subprocess.run(['oci', 'session', 'authenticate', '--no-browser'], 
                                    capture_output=True, text=True)
        return "oci_cli"
    except Exception as e:
        print(f"Cloud Shell auth setup failed: {e}")
        return None

def make_authenticated_request(endpoint, body, auth_method, tenancy_ocid, home_region):
    """Make an authenticated request using the appropriate method"""
    
    if auth_method == "oci_sdk":
        # Use OCI SDK authentication (original method)
        config = from_file()
        auth = Signer(
            tenancy=config['tenancy'],
            user=config['user'],
            fingerprint=config['fingerprint'],
            private_key_file_location=config['key_file'],
            pass_phrase=config['pass_phrase']
        )
        return requests.post(endpoint, json=body, auth=auth, timeout=300)
    
    elif auth_method == "cloud_shell" or auth_method == "oci_cli":
        # Use OCI CLI for authentication in Cloud Shell
        import subprocess
        import tempfile
        
        # Write request body to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(body, f)
            temp_file = f.name
        
        try:
            # Use OCI CLI to make the request
            cli_cmd = [
                'oci', 'raw-request',
                '--http-method', 'POST',
                '--target-uri', endpoint,
                '--request-body', f'file://{temp_file}',
                '--output', 'json'
            ]
            
            print(f"Debug: Running OCI CLI command: {' '.join(cli_cmd)}")
            result = subprocess.run(cli_cmd, capture_output=True, text=True, check=True)
            
            # Parse the CLI response
            cli_response = json.loads(result.stdout)
            
            # Create a mock response object
            class MockResponse:
                def __init__(self, data, status_code=200):
                    self._json_data = data
                    self.status_code = status_code
                    self.headers = {'Content-Type': 'application/json'}
                    
                def json(self):
                    return self._json_data
                    
                def raise_for_status(self):
                    if self.status_code >= 400:
                        raise requests.exceptions.HTTPError(f"{self.status_code} Error")
                        
                @property
                def content(self):
                    return json.dumps(self._json_data).encode('utf-8')
            
            return MockResponse(cli_response['data'])
            
        except subprocess.CalledProcessError as e:
            print(f"Debug: OCI CLI error: {e.stderr}")
            raise requests.exceptions.RequestException(f"OCI CLI failed: {e.stderr}")
        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    else:
        raise Exception("No suitable authentication method available")

def main():
    if len(sys.argv) < 4:
        print("Insufficient arguments. Usage:")
        print("  python3 collector_cloudshell.py tenancy_ocid home_region from to")
        print("  ./collector.sh tenancy_ocid home_region from to")
        print("Example: python3 collector_cloudshell.py ocid1.tenancy.oc1..foobarbar us-ashburn-1 2022-08-01 2022-08-22")
        print()
        print("Environment Detection:")
        print(f"  Cloud Shell: {is_cloud_shell()}")
        print(f"  OCI SDK Available: {OCI_SDK_AVAILABLE}")
        print(f"  Recommended Auth: {get_auth_method()}")
        return
    else:
        tenancy_ocid = str(sys.argv[1])
        home_region = str(sys.argv[2])
        from_date = str(sys.argv[3])
        to_date = str(sys.argv[4])
        call_endpoint(tenancy_ocid, home_region, from_date, to_date)

def call_endpoint(tenancy_ocid, home_region, from_date, to_date):
    # Detect environment and authentication method
    auth_method = get_auth_method()
    print(f"Debug: Detected environment - Cloud Shell: {is_cloud_shell()}")
    print(f"Debug: Using authentication method: {auth_method}")
    print(f"Debug: Tenancy OCID: {tenancy_ocid}")
    print(f"Debug: Using region: {home_region}")

    tz_adjustment = 'T00:00:00Z'
    from_date = from_date + tz_adjustment
    to_date = to_date + tz_adjustment
    endpoint = 'https://usageapi.' + home_region + '.oci.oraclecloud.com/20200107/usage'
    print(f"Debug: API endpoint: {endpoint}")
    print(f"Debug: Date range: {from_date} to {to_date}")
    
    body = {
        'tenantId': tenancy_ocid,
        'timeUsageStarted': from_date,
        'timeUsageEnded': to_date,
        'granularity': 'DAILY',  
        "queryType": "COST",
        "groupBy": [   
            "tagKey",
            "tagValue",
            "service",
            "compartmentPath",
        ],
        "compartmentDepth": 4,
    }
    
    print(f"Debug: Request body: {json.dumps(body, indent=2)}")
    print("Debug: Making API request...")
    
    try:
        response = make_authenticated_request(endpoint, body, auth_method, tenancy_ocid, home_region)
        print(f"Debug: Response status code: {response.status_code}")
        print(f"Debug: Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            print(f"Debug: Response content: {response.text if hasattr(response, 'text') else 'No text available'}")
        
        response.raise_for_status()
        print("Debug: API request successful!")
        print(f"Debug: Response size: {len(response.content)} bytes")
        
    except Exception as e:
        print(f"Debug: Request failed with error: {e}")
        print("\nTroubleshooting Tips:")
        if is_cloud_shell():
            print("- Ensure you're authenticated in Cloud Shell")
            print("- Try running: oci iam region list")
            print("- Check if you have proper permissions for Usage API")
        else:
            print("- Check your ~/.oci/config file")
            print("- Verify your API key permissions")
            print("- Ensure the tenancy OCID is correct")
        raise
    
    print("Debug: Parsing JSON response...")
    try:
        json_string = response.json()
        print(f"Debug: JSON parsed successfully. Type: {type(json_string)}")
        
        if isinstance(json_string, dict):
            print(f"Debug: JSON keys: {list(json_string.keys())}")
            # If it's a dict, check if it has 'items' key (common in OCI Usage API responses)
            if 'items' in json_string:
                print(f"Debug: Found 'items' key with {len(json_string['items'])} records")
            # Print size of each key
            for key, value in json_string.items():
                if isinstance(value, list):
                    print(f"Debug: Key '{key}' contains {len(value)} items")
                else:
                    print(f"Debug: Key '{key}' type: {type(value)}")
        elif isinstance(json_string, list):
            print(f"Debug: JSON list length: {len(json_string)}")
        
        print("Debug: Writing JSON to file (this may take a while for large responses)...")
        
        # Write JSON directly for Cloud Shell (simpler approach)
        with open('out.json', 'w') as f:
            json.dump(json_string, f, ensure_ascii=False, indent=2)
        print("Debug: JSON file written successfully!")
        
    except json.JSONDecodeError as e:
        print(f"Debug: JSON parsing failed: {e}")
        print("Debug: Raw response content (first 1000 chars):")
        content = response.content[:1000] if hasattr(response, 'content') else str(response)
        print(content)
        raise
    
    print("Debug: Creating DataFrame...")
    try:
        if isinstance(json_string, dict):
            # Check if this is an OCI Usage API response with 'items' key
            if 'items' in json_string and isinstance(json_string['items'], list):
                print("Debug: Processing OCI Usage API response with 'items' key")
                df = pd.DataFrame(json_string['items'])
                print(f"Debug: DataFrame created from items list with {len(json_string['items'])} records")
            else:
                print("Debug: Processing dictionary response")
                df = pd.DataFrame.from_dict(json_string, orient='index')
                print("Debug: DataFrame created from dict")
                df = df.transpose()
                print("Debug: DataFrame transposed")
        elif isinstance(json_string, list):
            print("Debug: Processing list response")
            df = pd.DataFrame(json_string)
            print("Debug: DataFrame created from list")
        else:
            print(f"Debug: Unexpected JSON type: {type(json_string)}")
            return
            
        print(f"Debug: DataFrame shape: {df.shape}")
        print("Debug: DataFrame columns:", list(df.columns) if len(df.columns) <= 10 else f"{len(df.columns)} columns")
        
        # Write CSV file
        print("Debug: Writing CSV file...")
        df.to_csv('output.csv', encoding='utf-8', index=False)
        print("Debug: CSV file written successfully!")
        
        # Get file sizes
        json_size = os.path.getsize('out.json') if os.path.exists('out.json') else 0
        csv_size = os.path.getsize('output.csv') if os.path.exists('output.csv') else 0
        print(f"Debug: Final output files created:")
        print(f"  - out.json: {json_size:,} bytes")
        print(f"  - output.csv: {csv_size:,} bytes")
        
    except Exception as e:
        print(f"Debug: DataFrame processing failed: {e}")
        print("Debug: JSON structure analysis:")
        if isinstance(json_string, dict):
            for key in json_string.keys():
                print(f"  - {key}: {type(json_string[key])}")
        raise

if __name__ == "__main__":
    main()