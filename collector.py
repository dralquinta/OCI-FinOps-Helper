# Copyright (c) 2022 Oracle and/or its affiliates.
# All rights reserved. The Universal Permissive License (UPL), Version 1.0 as shown at http://oss.oracle.com/licenses/upl

import requests
import sys
import pandas as pd
import json
from oci.config import from_file
from oci.signer import Signer
from datetime import date


def main():
    if len(sys.argv) < 4:
        print("Insuficient arguments. Usage. ./collector.sh tenancy_ocid home_region from to")
        print("example: ./collector.sh ocid1.tenancy.oc1..foobarbar us-ashburn-1 2022-08-01 2022-08-22")
    else:
        tenancy_ocid=str(sys.argv[1])
        home_region=str(sys.argv[2])
        from_date=str(sys.argv[3])
        to_date=str(sys.argv[4])
        call_endpoint(tenancy_ocid, home_region, from_date, to_date)
    

    

def call_endpoint(tenancy_ocid, home_region, from_date, to_date):
    config = from_file()
    print(f"Debug: Config loaded - tenancy: {config['tenancy']}")
    print(f"Debug: Using region: {home_region}")
    
    auth = Signer(
    tenancy=config['tenancy'],
    user=config['user'],
    fingerprint=config['fingerprint'],
    private_key_file_location=config['key_file'],
    pass_phrase=config['pass_phrase']
    )

    tz_adjustment='T00:00:00Z'
    from_date=from_date+tz_adjustment
    to_date=to_date+tz_adjustment
    endpoint = 'https://usageapi.'+home_region+'.oci.oraclecloud.com/20200107/usage'
    print(f"Debug: API endpoint: {endpoint}")
    print(f"Debug: Date range: {from_date} to {to_date}")
    body = {
    'tenantId': tenancy_ocid,
    'timeUsageStarted': from_date,
    'timeUsageEnded': to_date,
    'granularity': 'DAILY',  
    "queryType": "COST",
    "groupBy": [   
        "service",
        "compartmentPath",
        "skuPartNumber",
        "skuName",
    ],
    "compartmentDepth": 4,

    }
    
    print(f"Debug: Request body: {json.dumps(body, indent=2)}")
    print("Debug: Making API request...")
    
    try:
        response = requests.post(endpoint, json=body, auth=auth, timeout=60)
        print(f"Debug: Response status code: {response.status_code}")
        print(f"Debug: Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            print(f"Debug: Response content: {response.text}")
        
        response.raise_for_status()
        print("Debug: API request successful!")
        print(f"Debug: Response size: {len(response.content)} bytes")
        
    except requests.exceptions.Timeout:
        print("Debug: Request timed out after 60 seconds")
        raise
    except requests.exceptions.RequestException as e:
        print(f"Debug: Request failed with error: {e}")
        raise
    
    print("Debug: Parsing JSON response...")
    try:
        json_string=response.json()
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
        
        # Write JSON in chunks to provide progress feedback
        import os
        temp_file = 'out.json.tmp'
        with open(temp_file, 'w') as f:
            f.write('{\n')
            if isinstance(json_string, dict):
                total_keys = len(json_string)
                for i, (key, value) in enumerate(json_string.items()):
                    print(f"Debug: Writing key {i+1}/{total_keys}: {key}")
                    f.write(f'  "{key}": ')
                    json.dump(value, f, ensure_ascii=False, indent=2)
                    if i < total_keys - 1:
                        f.write(',')
                    f.write('\n')
            f.write('}')
        
        # Move temp file to final location
        os.rename(temp_file, 'out.json')
        print("Debug: JSON file written successfully!")
        
    except json.JSONDecodeError as e:
        print(f"Debug: JSON parsing failed: {e}")
        print("Debug: Raw response content (first 1000 chars):")
        print(response.text[:1000])
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
        print("Debug: DataFrame columns:", list(df.columns))
        
        # Write CSV in chunks if it's large
        print("Debug: Writing CSV file...")
        df.to_csv('output.csv', encoding='utf-8', index=False)
        print("Debug: CSV file written successfully!")
        print(f"Debug: Final output files created: out.json ({os.path.getsize('out.json')} bytes), output.csv ({os.path.getsize('output.csv')} bytes)")
        
    except Exception as e:
        print(f"Debug: DataFrame processing failed: {e}")
        print("Debug: JSON structure analysis:")
        if isinstance(json_string, dict):
            for key in json_string.keys():
                print(f"  - {key}: {type(json_string[key])}")
        raise 
    


    
if __name__ == "__main__":
    main() 