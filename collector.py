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

    response = requests.post(endpoint, json=body, auth=auth)
    response.raise_for_status()
    json_string=response.json()
    with open('out.json','w') as f:
        json.dump(json_string, f, ensure_ascii=False, indent=4)    
    f.close()
        
    df = pd.DataFrame.from_dict(json_string, orient='index')
    df = df.transpose()           
    df.to_csv('output.csv', encoding='utf-8', index=False) 
    


    
if __name__ == "__main__":
    main() 