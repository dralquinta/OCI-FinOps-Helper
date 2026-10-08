# Resource evidence for FinOps reduction reviews

Issue #6 expands the existing OCI CLI collection harness. Collection is read-only: it does not stop, delete, resize, apply, dismiss, or update cloud resources.

## Run

Use the existing modes:

```bash
# Cost, usage, Advisor resource actions, tags, inventory, attachments and monitoring
./collector.sh <tenancy_ocid> <home_region> <from_date> <to_date> --growth-collection

# Inventory, attachment evidence, tags, monitoring and existing growth collections
# Costs remain unknown because this mode intentionally skips cost and usage.
./collector.sh <tenancy_ocid> <home_region> <from_date> <to_date> --only-growth

# Recommendation summaries and affected-resource evidence
./collector.sh <tenancy_ocid> <home_region> <from_date> <to_date> --only-recommendations
```

Use `YYYY-MM-DD` dates. Monitoring now uses the same exclusive end boundary as the Usage API. Supply the tenancy home region for Advisor and usage. Other inventory and monitoring queries discover subscribed READY regions and explicitly scope requests to accessible active compartments, including the root tenancy.

Normal collection without `--growth-collection` retains the existing cost/usage workflow; Advisor gains resource-level evidence. No new authentication mechanism is introduced: the configured OCI CLI profile/session continues to apply.

## Collected APIs and evidence

| Source | Read operation | Evidence and limits |
| --- | --- | --- |
| Region/compartment discovery | `iam region-subscription list`, `iam compartment list` | Raw discovery records; READY regions; active compartment subtree and root; discovery failure explicitly reported. |
| Resource Search | `search resource structured-search` | `query all resources`, explicit page tokens, raw indexed resource metadata. Search sees supported indexed types and only IAM-visible resources. |
| Compute | `compute instance list` | Shape/configuration, lifecycle, tags, timestamps and other returned fields. |
| Block storage | `bv volume list`, `compute volume-attachment list` | Raw volumes and attachment relationships across compartments. |
| Boot storage | `bv boot-volume list`, `compute boot-volume-attachment list` | Raw inventory/attachments, scoped by regional availability domain. |
| Monitoring | `monitoring metric list`, `monitoring metric-data summarize-metrics-data` | Discover available metric names, query hourly means, retain all returned streams/dimensions/datapoints and coverage. |
| Cloud Advisor | `optimizer recommendation-summary list`, `optimizer resource-action-summary list` | Existing summaries plus action/resource/recommendation IDs, status, savings, metadata and extended metadata. |
| Actual costs | Usage API `RequestSummarizedUsages` through existing `raw-request` | Explicit next-page traversal retaining the request body; incomplete cost pages are rejected rather than reported as complete. |

List operations use `--all` where supported. Search instead follows the CLI's top-level `opc-next-page` token with `--page`. SummarizeMetricsData has no `--all`; its streams are retained without the previous 100-stream sample truncation. CLI/raw-request pagination is handled according to each API's response shape.

Monitoring discovers names in `oci_computeagent`, `oci_blockstore`, `oci_vcn`, `oci_database`, `oci_autonomous_database`, `oci_lbaas`, `oci_nlb` and `oci_objectstorage`. This provides utilization/activity evidence for compute, storage, networking, databases and load balancers; it does not pretend every service exposes identical metrics. Query coverage records include region, compartment, namespace, metric and time window. Requests are partitioned into at most 90-day windows. Hourly retention is measured from request time: historical data outside retention, disabled agents, missing metrics and denied access remain unknown.

## Outputs

- `finops_collection.json`: raw regional inventory/discovery, collection coverage, reduction review candidates and cost context.
- `finops_candidates.csv`: review candidates with observed cost separated by currency and unknown-cost status.
- `finops_summary.txt`: scope, inventory counts, candidate counts and failed coverage.
- `growth_collection_tags.json`: existing growth output with `finops` evidence and complete performance metric streams.
- `growth_collection_summary.txt`: existing growth summary, including FinOps evidence coverage.
- `recommendations.json`: existing `items` plus complete `resource_actions`, collection `coverage` and USD savings metadata.
- `recommendations.out`: summaries, affected-resource evidence and coverage warnings.

Collected resource names, OCIDs and metadata may be sensitive operational data. Store outputs in your existing protected output location; they are not repository fixtures.

## Interpreting candidates and money

Stopped compute is a review candidate, not an automatic claim of savings. Billing depends on shape, and associated storage can continue to incur costs. Volumes must be AVAILABLE and have no live or transitional attachment before becoming unattached review candidates. Classification requires successful attachment discovery across every scanned compartment in the region; missing, malformed or failed coverage prevents an orphan claim. Boot volumes also require complete availability-domain coverage. Intentional retained volumes still require owner review.

No metric data does not mean zero usage. Low CPU alone is not a deletion rule; preserve evidence for workload-aware rightsizing. This feature does not apply arbitrary utilization thresholds or claim a recommended deletion is safe.

Actual candidate costs aggregate raw COST items by resource OCID, region and actual billing currency. They are observed costs for the requested interval, not guaranteed future savings. Missing/invalid costs remain unknown, and confirmed zero remains zero. They do not use the merged cost/usage dataframe, which can repeat billing rows across usage SKUs. Credits and adjustments remain part of the observed amount.

Cloud Advisor savings estimates are USD and remain USD regardless of `--currency`. The requested display currency is preserved as metadata; no unsupported currency conversion is performed. Resource-action amounts are not added again to recommendation summary totals. Estimates can overlap and are not guaranteed realized savings.

Partial source failures are saved in coverage, while independent collections continue. Discovery fallback to the home region/root is explicitly incomplete. A failed requested billing stage makes the overall workflow return failure while allowing inventory collection to finish. Outputs should be evaluated together with coverage rather than treated as proof of complete tenancy visibility.

## Permissions

Use read-only IAM grants for the resources and evidence you need, scoped to the authorized tenancy/compartments. Advisor uses `optimizer-api-family`, not `cloud-advisor-family`:

```text
Allow group <YourGroup> to read optimizer-api-family in tenancy
```

Advisor metadata requires the additional resource permissions documented by Oracle. Monitoring requires access to metrics and the monitored resources; inventory requires the corresponding compute, volume, search and identity permissions. Usage requires cost/usage access. The helper does not require manage permissions or modify IAM policies. Denied sources appear in collection coverage.

## Official references

- [Search queries and indexed resource scope](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/samplequeries.htm)
- [Search structured-search CLI and pagination](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/search/resource/structured-search.html)
- [Volume attachment CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/volume-attachment/list.html)
- [Boot volume attachment CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/boot-volume-attachment/list.html)
- [Advisor resource-action CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action-summary/list.html)
- [Advisor fields](https://docs.oracle.com/en-us/iaas/tools/python/2.159.0/api/optimizer/models/oci.optimizer.models.ResourceActionSummary.html)
- [Advisor categories and supported services](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/recommendations.htm)
- [Advisor IAM reference](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Reference/cloudadvisorpolicyreference.htm)
- [Monitoring summarize CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/monitoring/metric-data/summarize-metrics-data.html)
- [Monitoring resolution and retention](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/query-metric-resolution.htm)
- [Compute metric reference](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm)
- [Block volume metric reference](https://docs.oracle.com/en-us/iaas/Content/Block/References/volumemetrics-reference.htm)
- [Usage query pagination](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html)
- [Stopped-instance billing by shape](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm)

## Validation

External OCI services are mocked. Run `python3 -m unittest discover -s tests -v`. Live tenancy collection is not part of automated verification; real coverage depends on authorization, service availability, monitoring agents, retention and subscription state.
