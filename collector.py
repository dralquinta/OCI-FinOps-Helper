import requests
import pandas as pd
import json
from oci.config import from_file
from oci.signer import Signer

OCID=''

def main():

    config = from_file()
    auth = Signer(
    tenancy=config['tenancy'],
    user=config['user'],
    fingerprint=config['fingerprint'],
    private_key_file_location=config['key_file'],
    pass_phrase=config['pass_phrase']
    )
    response = call_endpoint(auth)
    print(response)

    

def call_endpoint(auth):
    endpoint = 'https://usageapi.us-ashburn-1.oci.oraclecloud.com/20200107/usage'
    body = {
    'tenantId': 'ocid1.tenancy.oc1..aaaaaaaaoqdygmiidrabhv3y4hkr3rb3z6dpmgotvq2scffra6jt7rubresa',
    'timeUsageStarted': '2022-12-01T00:00:00Z',
    'timeUsageEnded': '2022-12-29T00:00:00Z',
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
    df.to_csv('csvfile.csv', encoding='utf-8', index=False)
    
    

    
   
   
    return response    


    
if __name__ == "__main__":
    main() 