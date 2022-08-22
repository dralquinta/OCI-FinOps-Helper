# cost_report

To excecute: 

```shell
$ ./collector.sh ocid1.tenancy.oc1..aaaaaaaaoqfoobar us-ashburn-1 2022-08-02 2022-08-03
/home/opc/REPOS/cost_report/venv/lib64/python3.6/site-packages/oci/_vendor/httpsig_cffi/sign.py:10: CryptographyDeprecationWarning: Python 3.6 is no longer supported by the Python core team. Therefore, support for it is deprecated in cryptography and will be removed in a future release.
  from cryptography.hazmat.backends import default_backend  # noqa: F401
```

This will generate a json file named `output.json` similar to this: 

```json
{
    "groupBy": [
        "service",
        "compartmentPath"
    ],
    "items": [
        {
            "tenantId": null,
            "tenantName": null,
            "compartmentId": null,
            "compartmentPath": "yourcloudtenancy/compartment",
            "compartmentName": null,
            "service": "Block Storage",
            "resourceName": null,
            "resourceId": null,
            "region": null,
            "ad": null,
            "weight": null,
            "shape": null,
            "skuPartNumber": null,
            "skuName": null,
            "unit": null,
            "discount": null,
            "listRate": null,
            "platform": null,
            "timeUsageStarted": "2020-12-26T00:00:00.000Z",
            "timeUsageEnded": "2020-12-27T00:00:00.000Z",
            "computedAmount": null,
            "computedQuantity": 25.922896550163,
            "overagesFlag": null,
            "unitPrice": null,
            "currency": " ",
            "subscriptionId": null,
            "overage": null,
            "isForecast": false,
            "tags": [
                {
                    "namespace": null,
                    "key": null,
                    "value": null
                }
            ]
        },
```

It will also generate a file called `output.csv` which can be later worked in Excel. 


You can play with the request body to add more details on the results. More details on how to use the API in the [following link](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#cost_analysis_using_the_api)

Value that corresponds to cost is determined by entry `computedAmount`