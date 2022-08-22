# cost_report

To excecute: 

./collector.sh

This will generate a json file similar to this: 

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
            "compartmentPath": "ecrcloud/siva",
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


You can play with the request body to add more details on the results. More details on how to use the API in the [following link](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#cost_analysis_using_the_api)