#!/usr/bin/env python3

import requests
import json
from oci.config import from_file
from oci.signer import Signer

def test_usage_response():
    config = from_file()
    auth = Signer(
        tenancy=config['tenancy'],
        user=config['user'],
        fingerprint=config['fingerpoint'],
        private_key_file_location=config['key_file'],
        pass_phrase=config['pass_phrase']
    )
    
    usage_endpoint = "https://usageapi.us-ashburn-1.oci.oraclecloud.com/20200107/usage"
    
    # Test with just one day first
    body = {
        'tenantId': config['tenancy'],
        'timeUsageStarted': '2025-10-01T00:00:00Z',
        'timeUsageEnded': '2025-10-02T00:00:00Z',
        'granularity': 'DAILY',  
        "queryType": "COST"
    }
    
    response = requests.post(usage_endpoint, json=body, auth=auth, timeout=30)
    result = response.json()
    
    print("Response structure:")
    print(f"Keys: {list(result.keys())}")
    print(f"Items count: {len(result.get('items', []))}")
    
    if result.get('items'):
        print("\nFirst item keys:")
        print(list(result['items'][0].keys()))
        print("\nFirst item:")
        print(json.dumps(result['items'][0], indent=2))

if __name__ == "__main__":
    test_usage_response()