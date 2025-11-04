#!/usr/bin/env python3

import requests
import json
from oci.config import from_file
from oci.signer import Signer

def test_auth():
    print("Testing OCI authentication...")
    
    # Load config
    try:
        config = from_file()
        print(f"✓ Config loaded - tenancy: {config['tenancy']}")
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return
    
    # Create signer
    try:
        auth = Signer(
            tenancy=config['tenancy'],
            user=config['user'],
            fingerprint=config['fingerprint'],
            private_key_file_location=config['key_file'],
            pass_phrase=config['pass_phrase']
        )
        print("✓ Signer created")
    except Exception as e:
        print(f"✗ Failed to create signer: {e}")
        return
    
    # Test with a simple API call first (Identity service)
    print("\nTesting with Identity service...")
    identity_endpoint = "https://identity.us-ashburn-1.oraclecloud.com/20160918/compartments"
    
    params = {
        "compartmentId": config['tenancy'],
        "limit": 1
    }
    
    try:
        print("Making Identity API request...")
        response = requests.get(identity_endpoint, params=params, auth=auth, timeout=30)
        print(f"Identity API response: {response.status_code}")
        if response.status_code != 200:
            print(f"Identity API error: {response.text}")
        else:
            print("✓ Identity API works - authentication is valid")
    except Exception as e:
        print(f"✗ Identity API failed: {e}")
        return
    
    # Now test Usage API with minimal request
    print("\nTesting Usage API...")
    usage_endpoint = "https://usageapi.us-ashburn-1.oci.oraclecloud.com/20200107/usage"
    
    # Minimal request body
    body = {
        'tenantId': config['tenancy'],
        'timeUsageStarted': '2025-10-01T00:00:00Z',
        'timeUsageEnded': '2025-10-02T00:00:00Z',  # Just 1 day
        'granularity': 'DAILY',  
        "queryType": "COST"
    }
    
    try:
        print("Making Usage API request...")
        print(f"Request body: {json.dumps(body, indent=2)}")
        response = requests.post(usage_endpoint, json=body, auth=auth, timeout=30)
        print(f"Usage API response: {response.status_code}")
        if response.status_code != 200:
            print(f"Usage API error: {response.text}")
        else:
            print("✓ Usage API works!")
            result = response.json()
            print(f"Response type: {type(result)}")
            if isinstance(result, dict):
                print(f"Response keys: {list(result.keys())}")
    except Exception as e:
        print(f"✗ Usage API failed: {e}")

if __name__ == "__main__":
    test_auth()