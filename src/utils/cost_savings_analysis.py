"""Offline, evidence-backed cost reviews; never executes cloud commands."""

import csv
import html
import json
import math
import shlex
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_evidence(directory):
    """Prefer original COST records; merged joins can multiply billing rows."""
    directory = Path(directory)
    def read(name, required=False):
        path = directory / name
        if not path.exists():
            if required:
                raise ValueError(f'Missing {name}; collect COST and USAGE to generate out.json')
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as error:
            raise ValueError(f'Cannot read {name}: {error}') from error
    return read('out.json', True), read('finops_collection.json'), read('recommendations.json')


def _number(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'Invalid {field}: expected a finite number') from error
    if isinstance(value, bool) or not math.isfinite(result):
        raise ValueError(f'Invalid {field}: expected a finite number')
    return result


def _provider_flag(value):
    """OCI extended metadata can encode booleans as strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in ('true', 'yes', '1'):
            return True
        if token in ('false', 'no', '0', ''):
            return False
    return None


def _execution(kind, resource_id, region):
    commands = {
        'volume': ('bv volume delete', '--volume-id'),
        'boot_volume': ('bv boot-volume delete', '--boot-volume-id'),
        'instance': ('compute instance action', '--instance-id'),
    }
    if kind == 'instance':
        what = 'Review stopped compute billing and associated storage; consider an owner-approved operating schedule or retirement.'
        how = 'Confirm the stopped state, shape billing rules, workloads and associated disks. A stopped instance alone does not prove savings; do not terminate automatically.'
        rollback = 'For approved scheduling, start the instance again and restore its application schedule. Retirement requires a separate recovery design.'
    elif kind in ('volume', 'boot_volume'):
        what = 'Review removal of an unattached disk to avoid future eligible storage charges.'
        how = 'Recheck attachments in its region and compartment, obtain owner retention approval, create and test a backup, then approve disk deletion during a change window.'
        rollback = 'Deletion is irreversible; restore a tested backup into a NEW volume and reattach. Resource identifiers will change; recovery is not guaranteed without a tested backup.'
    else:
        what = 'Review the Advisor action and verify that it reduces billed spend.'
        how = 'Unknown or unsupported command mapping: open the Advisor recommendation and resource in the OCI Console; follow the service-specific runbook after owner approval.'
        rollback = 'Document and test a service-specific rollback before approval; destructive changes may be irreversible.'
    command = 'Unavailable: resource identity/region or a validated service-specific command mapping is missing.'
    if kind in commands and isinstance(resource_id, str) and resource_id and isinstance(region, str) and region and region != 'Unknown':
        operation, flag = commands[kind]
        command = f'oci {operation} {flag} {shlex.quote(resource_id)} --region {shlex.quote(region)}'
        if kind == 'instance':
            command += ' --action START  # recovery template; not a savings action'
    return {
        'what': what, 'how': how, 'command': command,
        'prerequisites': 'Owner and change approval; current IAM access; validate resource identity, region, dependencies, retention and backup recovery; inspect current inventory and billing.',
        'risk': 'Service outage, loss of data or retention compliance, recovery cost; inventory and Advisor estimates may be stale.',
        'rollback': rollback,
        'verification': 'Re-query lifecycle and attachments; validate application health and recovery; compare complete post-change billing periods in the same currency, excluding refunds and unrelated changes.',
    }


def analyze(raw, finops=None, advisor=None):
    """Build currency-safe spend summaries and a non-additive review backlog."""
    call = raw.get('call1') if isinstance(raw, dict) else None
    rows = call.get('items') if isinstance(call, dict) else None
    if not isinstance(rows, list):
        raise ValueError('out.json requires call1.items original COST records')
    totals = defaultdict(float)
    services = defaultdict(float)
    resources = defaultdict(lambda: defaultdict(float))
    locations = defaultdict(list)
    daily = defaultdict(float)
    resource_spend = defaultdict(float)
    compartment_spend = defaultdict(float)
    starts, ends = [], []
    warnings = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('call1.items must contain objects')
        amount = _number(row.get('computedAmount', row.get('computed-amount')), 'computedAmount')
        currency = row.get('currency') or 'Unknown'
        service = row.get('service') or 'Unknown'
        resource = row.get('resourceId', row.get('resource-id'))
        region = row.get('region')
        if not all(isinstance(value, str) for value in (currency, service)):
            raise ValueError('Currency and service must be strings')
        totals[currency] += amount
        services[service, currency] += amount
        resource_spend[resource or 'Unknown', region or 'Unknown', service, currency] += amount
        compartment_spend[row.get('compartmentPath') or 'Unknown', currency] += amount
        if resource:
            resources[resource, region][currency] += amount
            locations[resource].append(row)
        for camel, hyphen, values in [('timeUsageStarted', 'time-usage-started', starts),
                                       ('timeUsageEnded', 'time-usage-ended', ends)]:
            value = row.get(camel, row.get(hyphen))
            if value is not None:
                try:
                    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValueError(f'Invalid {camel}: expected an ISO timestamp') from error
                values.append(parsed)
        day = row.get('timeUsageStarted', row.get('time-usage-started', 'Unknown'))
        daily[str(day)[:10], currency] += amount
    if 'Unknown' in totals:
        warnings.append('Missing billing currency: Unknown amounts cannot be compared to USD estimates.')
    for label, evidence in [('FinOps', finops), ('Advisor', advisor)]:
        if evidence is None:
            warnings.append(f'{label} evidence missing; collect it to expand the review backlog.')
        elif not isinstance(evidence, dict):
            raise ValueError(f'{label} evidence must be an object')
    if finops:
        if finops.get('discovery_complete') is not True:
            warnings.append('FinOps discovery incomplete or unknown; candidate completeness is unproven.')
        for item in finops.get('coverage', []):
            if item.get('status') == 'failed':
                warnings.append(f"FinOps failed coverage: {item.get('operation', 'Unknown')} / {item.get('region', 'Unknown')}")
    if advisor and advisor.get('coverage', {}).get('resource_actions', {}).get('status') != 'complete':
        warnings.append('Advisor resource action coverage incomplete or unknown.')
    actions = []
    seen = set()

    def add(source, item):
        resource = item.get('resource_id') if source == 'FinOps' else item.get('resource-id')
        records = locations.get(resource, [])
        billing_regions = {row.get('region') for row in records if row.get('region')}
        extended = item.get('extended-metadata') or {}
        if not isinstance(extended, dict):
            extended = {}
        region = item.get('region') or extended.get('region') or (next(iter(billing_regions)) if len(billing_regions) == 1 else 'Unknown')
        kind = item.get('resource_type', item.get('resource-type', 'Unknown'))
        identity = item.get('id') or (resource, region, kind, item.get('reason', item.get('action')))
        key = source, str(identity)
        if key in seen:
            return
        seen.add(key)
        regional_records = [row for row in records if row.get('region') in (region, None)] if region != 'Unknown' else []
        record = regional_records[0] if regional_records else {}
        observed = dict(resources.get((resource, region), {}))
        if len(billing_regions) <= 1:
            for currency, amount in resources.get((resource, None), {}).items():
                observed[currency] = observed.get(currency, 0) + amount
        savings = None
        if source.startswith('Advisor') and item.get('estimated-cost-saving') is not None:
            savings = _number(item['estimated-cost-saving'], 'estimated-cost-saving')
        provider_action = item.get('action')
        action_label = item.get('reason', provider_action)
        if isinstance(action_label, dict):
            action_label = action_label.get('type') or 'Unknown'
        if not isinstance(action_label, str) or not action_label:
            action_label = 'Unknown'
        status = item.get('status', 'REVIEW_REQUIRED')
        if _provider_flag(extended.get('noLongerRecommend')) is True:
            status = 'NO_LONGER_RECOMMENDED'
        calculation_error = extended.get('estimatedSavingCalculationError')
        error_flag = _provider_flag(calculation_error)
        if error_flag is True or (error_flag is None and isinstance(calculation_error, str) and calculation_error.strip()):
            status = 'ESTIMATE_ERROR'
            warnings.append(f'Advisor estimate calculation error for {resource or "Unknown"}: {calculation_error}')
        action = {
            'source': source, 'action_id': item.get('id', 'Unknown'),
            'recommendation_id': item.get('recommendation-id', item.get('id', 'Unknown') if source == 'Advisor summary' else 'Unknown'),
            'recommendation_name': item.get('name', 'Unknown'),
            'recommendation_category': item.get('category-id', item.get('category', 'Unknown')),
            'recommendation_description': item.get('description', 'Unknown'),
            'affected_resource_counts': item.get('resource-counts', []),
            'resource_id': resource or 'Unknown', 'resource_name': item.get('display_name', item.get('resource-name', item.get('name', record.get('resourceName', 'Unknown')))),
            'resource_type': kind, 'region': region,
            'compartment_id': item.get('compartment_id', item.get('compartment-id', 'Unknown')),
            'compartment_name': item.get('compartment-name', 'Unknown'),
            'compartment_path': record.get('compartmentPath', 'Unknown'),
            'service': record.get('service', 'Unknown'),
            'action': action_label,
            'provider_action': provider_action,
            'status': status,
            'observed_costs': observed,
            'estimated_monthly_savings_usd': savings,
            'evidence_gaps': 'Evidence missing or ambiguous: validate unknown identity, region, ownership, utilization, dependency, billing and recovery fields before approval.',
            'provider_metadata': item.get('metadata', {}),
            'provider_extended_metadata': item.get('extended-metadata', {}),
            'provider_evidence': item,
            'savings_note': ('Advisor summary-only estimate: excluded from screening total; obtain affected resource actions and inventory first. ' if source == 'Advisor summary' else '') + 'Observed cost is not savings; Advisor estimates may overlap other actions and category summaries. Never add these sources. Currency conversion is not performed.',
            'where': f"OCI Console: Governance & Administration > Cloud Advisor for recommendations; Storage > Block/Boot Volumes or Compute > Instances for mapped inventory types. Region {region}; service {record.get('service', 'Unknown')}; compartment ID {item.get('compartment_id', item.get('compartment-id', 'Unknown'))}; compartment path {record.get('compartmentPath', 'Unknown')}; resource {resource or 'Unknown'}; Advisor recommendation {item.get('recommendation-id', item.get('id', 'Unknown') if source == 'Advisor summary' else 'Unknown')}",
            **_execution(kind if source == 'FinOps' else 'advisor', resource, region),
        }
        actions.append(action)
    for item in (finops or {}).get('candidates', []):
        add('FinOps', item)
    for item in (advisor or {}).get('resource_actions', []):
        add('Advisor', item)
    for item in (advisor or {}).get('items', []):
        add('Advisor summary', item)
    actions.sort(key=lambda a: (a['estimated_monthly_savings_usd'] or 0), reverse=True)
    # Select only one pending estimate per identified resource. Missing identities cannot be summed.
    estimates = {}
    for action in actions:
        saving = action['estimated_monthly_savings_usd']
        if action['source'] == 'Advisor' and action['status'] == 'PENDING' and action['resource_id'] != 'Unknown' and saving is not None and saving > 0:
            key = action['resource_id']
            estimates[key] = max(estimates.get(key, 0), saving)
    period = {'start': min(starts).isoformat() if starts else 'Unknown', 'end_exclusive': max(ends).isoformat() if ends else 'Unknown',
              'missing_start_rows': len(rows) - len(starts), 'missing_end_rows': len(rows) - len(ends)}
    return {'measurement_period': period, 'totals': dict(totals), 'services': [{'service': s, 'currency': c, 'observed_cost': v} for (s, c), v in sorted(services.items())],
            'resources': [{'resource_id': r, 'region': region, 'service': service, 'currency': c, 'observed_cost': v} for (r, region, service, c), v in sorted(resource_spend.items())],
            'compartments': [{'compartment_path': path, 'currency': c, 'observed_cost': v} for (path, c), v in sorted(compartment_spend.items())],
            'daily': [{'date': d, 'currency': c, 'observed_cost': v} for (d, c), v in sorted(daily.items())],
            'actions': actions, 'warnings': warnings,
            'advisor_estimates_usd': sum(estimates.values()),
            'estimate_method': 'Screening scenario: at most the highest positive PENDING Advisor estimate per identified resource. Cross-resource dependencies may still overlap; not a committed savings target. Category summaries and inventory costs excluded.'}


def export_reports(report, directory):
    """Export a portable executive briefing and detailed implementation appendix."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prepared = datetime.now(timezone.utc).isoformat()
    def top(rows):
        currencies = sorted({row['currency'] for row in rows})
        return [row for currency in currencies
                for row in sorted((r for r in rows if r['currency'] == currency),
                                  key=lambda r: r['observed_cost'], reverse=True)[:10]]
    lines = ['# Executive cost savings review', '', f'Prepared at: {prepared} (UTC)', '', '## Financial baseline', '',
             'Observed spend covers the collected interval; it is not a monthly savings estimate. Refunds are retained. No currencies are combined.',
             f"Measurement period (end exclusive): {json.dumps(report['measurement_period'])}", '']
    for currency, amount in sorted(report['totals'].items()):
        lines.append(f'- {currency}: {amount:,.2f}')
    lines += ['', '## Savings screening scenario', '',
              f"Advisor screening estimate: {report['advisor_estimates_usd']:,.2f} USD/month.",
              report['estimate_method'], '', '## Spend by service and currency', '']
    lines += [f"- {item['service']} / {item['currency']}: {item['observed_cost']:,.2f}" for item in top(report['services'])]
    lines += ['', '## Spend by resource (top 10 per currency)', '', '[Complete resource spend CSV](cost_savings_resources.csv)', '']
    lines += [f"- {item['resource_id']} / {item['region']} / {item['service']} / {item['currency']}: {item['observed_cost']:,.2f}" for item in top(report['resources'])]
    lines += ['', '## Spend by compartment (top 10 per currency)', '', '[Complete compartment spend CSV](cost_savings_compartments.csv)', '']
    lines += [f"- {item['compartment_path']} / {item['currency']}: {item['observed_cost']:,.2f}" for item in top(report['compartments'])]
    lines += ['', '## Action and status summary', '']
    counts = defaultdict(int)
    for action in report['actions']:
        counts[action['action'], action['status']] += 1
    lines += [f'- {action} / {status}: {count} review actions' for (action, status), count in sorted(counts.items())]
    lines += ['', '## Unknowns and collection gaps', ''] + [f'- {warning}' for warning in report['warnings']]
    lines += ['', '## Approval and prioritization checklist', '',
              '- [ ] Assign a resource owner and validate current evidence.',
              '- [ ] Prioritize positive pending Advisor estimates; then investigate high spend within each currency.',
              '- [ ] Validate dependencies, backups, retention, utilization and rollback before change approval.',
              '- [ ] Select mutually exclusive actions per resource; reconcile cross-resource dependencies.',
              '- [ ] Record approved scenario assumptions and actual execution dates.',
              '- [ ] Compare equivalent post-change billing windows and explain external changes.',
              '', '## Unassessed areas and evidence collection', '',
              '- Compute/database rightsizing: collect CPU, memory, I/O and peak/seasonal utilization for at least a representative billing period; validate minimum capacity, HA and performance SLOs.',
              '- Licensing and commitments: obtain contract terms, BYOL eligibility, license inventory, reservation/commitment coverage and renewal dates from procurement; marginal savings may differ from list prices.',
              '- Storage performance/tiering: collect VPU configuration, throughput/IOPS, access ages, retrieval and minimum-retention charges, backups and lifecycle policies; benchmark before changing tiers.',
              '- Scheduling: obtain workload calendars, timezone, dependency startup order, exclusions and application restart tests; verify shape-specific stop billing.',
              '- Networking/other services: inspect SKU charges, transfer destinations, gateways, load balancers and retention with owners; collect service-specific metrics before proposing reductions.',
              '', '## Per-resource execution appendix', '']
    for index, action in enumerate(report['actions'], 1):
        lines += [f'### Review action {index}', '']
        for key, value in action.items():
            lines.append(f'- {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value}')
        lines.append('')
    if not report['actions']:
        lines.append('No evidence-backed actions available. Collect FinOps and Advisor evidence; spend alone does not establish safe savings.')
    content = '\n'.join(lines) + '\n'
    paths = {'markdown': directory / 'cost_savings_executive.md', 'html': directory / 'cost_savings_executive.html',
             'csv': directory / 'cost_savings_actions.csv', 'resources_csv': directory / 'cost_savings_resources.csv',
             'compartments_csv': directory / 'cost_savings_compartments.csv'}
    paths['markdown'].write_text(content, encoding='utf-8')
    def escape(value):
        return html.escape(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
    def table(rows, columns):
        headings = ''.join(f'<th>{escape(label)}</th>' for _, label in columns)
        body = ''.join('<tr>' + ''.join(f'<td>{escape(row.get(key, "Unknown"))}</td>' for key, _ in columns) + '</tr>' for row in rows)
        return f'<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table>'
    page = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Executive cost savings review</title>',
            '<style>body{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;color:#182534;padding:1rem}h1,h2,h3{color:#173d57}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #cbd5df;padding:.55rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eaf0f5}details{margin:1rem 0}a{color:#12618a}@media print{body{font-size:10pt;margin:0;max-width:none}thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}a{color:inherit}}</style></head><body>',
            '<h1>Executive cost savings review</h1>', f'<p>Prepared at: {escape(prepared)} (UTC)</p>',
            '<h2>Financial baseline</h2><p>Observed spend for the collected interval; refunds retained. Currencies are never combined. Observed cost is not guaranteed savings.</p>',
            table([{'currency': c, 'observed_cost': v} for c, v in sorted(report['totals'].items())], [('currency', 'Currency'), ('observed_cost', 'Observed spend')]),
            '<h3>Measurement period</h3>', table([report['measurement_period']], [(key, key.replace('_', ' ').title()) for key in report['measurement_period']]),
            '<h2>Savings screening scenario</h2>', f'<p>{escape(report["advisor_estimates_usd"])} USD/month. {escape(report["estimate_method"])}</p>',
            '<h2>Spend drivers: top 10 per currency</h2><h3>Services</h3>',
            table(top(report['services']), [('service', 'Service'), ('currency', 'Currency'), ('observed_cost', 'Observed spend')]),
            '<h3>Resources</h3><p><a href="cost_savings_resources.csv">Complete resource spend CSV</a></p>',
            table(top(report['resources']), [('resource_id', 'Resource'), ('region', 'Region'), ('service', 'Service'), ('currency', 'Currency'), ('observed_cost', 'Observed spend')]),
            '<h3>Compartments</h3><p><a href="cost_savings_compartments.csv">Complete compartment spend CSV</a></p>',
            table(top(report['compartments']), [('compartment_path', 'Compartment'), ('currency', 'Currency'), ('observed_cost', 'Observed spend')]),
            '<h2>Action and status summary</h2>',
            table([{'action': action, 'status': status, 'count': count} for (action, status), count in sorted(counts.items())], [('action', 'Action'), ('status', 'Status'), ('count', 'Review count')]),
            '<h2>Unknowns and collection gaps</h2><ul>' + ''.join(f'<li>{escape(warning)}</li>' for warning in report['warnings']) + '</ul>',
            '<h2>Approval and evidence checklist</h2><ul>']
    checklist = content.split('## Approval and prioritization checklist\n', 1)[1].split('## Per-resource execution appendix', 1)[0]
    for line in checklist.splitlines():
        if line.startswith('- '):
            page.append(f'<li>{escape(line[2:])}</li>')
        elif line.startswith('## '):
            page.append(f'</ul><h3>{escape(line[3:])}</h3><ul>')
    page += ['</ul><h2>Per-resource execution appendix</h2><p><a href="cost_savings_actions.csv">Complete action backlog CSV</a></p>']
    for index, action in enumerate(report['actions'], 1):
        page += [f'<h3>Review {index}: {escape(action["resource_id"])} / {escape(action["action"])}</h3>',
                 table([{'field': key, 'detail': value} for key, value in action.items()], [('field', 'Field'), ('detail', 'Evidence / execution detail')])]
    if not report['actions']:
        page.append('<p>No evidence-backed actions available. Collect FinOps and Advisor evidence; spend alone does not establish safe savings.</p>')
    page.append('</body></html>')
    paths['html'].write_text('\n'.join(page), encoding='utf-8')
    fields = list(report['actions'][0]) if report['actions'] else ['source', 'resource_id', 'region', 'action', 'status', 'observed_costs', 'estimated_monthly_savings_usd']
    fields += ['owner', 'approval_date', 'execution_date', 'baseline_period', 'comparison_period',
               'verified_savings', 'verified_currency', 'verification_evidence', 'outcome_notes']
    with paths['csv'].open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for action in report['actions']:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in action.items()})
    for name, rows, fields in [('resources_csv', report['resources'], ['resource_id', 'region', 'service', 'currency', 'observed_cost']),
                               ('compartments_csv', report['compartments'], ['compartment_path', 'currency', 'observed_cost'])]:
        with paths[name].open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return paths
