"""Read-only regional inventory and evidence for FinOps resource reviews."""

import csv
import json
import math
import subprocess
try:
    from ..distribution import run_oci
except ImportError:  # Direct src/collector.py execution
    from distribution import run_oci
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


class OCIFinOpsCollector:
    """Collect inventory without treating missing evidence as idle resources."""

    def __init__(self, tenancy_ocid, home_region, output_dir='output', execute_command=None):
        self.tenancy_ocid = tenancy_ocid
        self.home_region = home_region
        self.output_dir = Path(output_dir)
        self.execute_command = execute_command or self._execute

    @staticmethod
    def _execute(command, description):
        result = run_oci(command, capture_output=True, text=True, timeout=300)
        if result.returncode:
            return None
        response = json.loads(result.stdout)
        return response if command[1:4] == ['search', 'resource', 'structured-search'] else response.get('data')

    @staticmethod
    def _items(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get('items'), list):
            return data['items']
        return None

    @staticmethod
    def _valid_records(records):
        identity_fields = ('id', 'identifier', 'region-name', 'name', 'volume-id', 'boot-volume-id', 'compartment-id')
        return records is not None and all(
            isinstance(item, dict) and all(item.get(field) is None or isinstance(item[field], str) for field in identity_fields)
            for item in records)

    def _search_pages(self, command, operation):
        """Search lacks --all; its CLI JSON exposes opc-next-page headers."""
        records = []
        seen_pages = set()
        while True:
            try:
                response = self.execute_command(command, operation)
                data = response.get('data', response) if isinstance(response, dict) else response
                page_records = self._items(data)
                if not self._valid_records(page_records):
                    return records, 'Search page failed or contained invalid resource records'
                records.extend(page_records)
                page = response.get('opc-next-page') if isinstance(response, dict) else None
                if not page:
                    return records, None
                if not isinstance(page, str) or page in seen_pages:
                    return records, 'Search returned an invalid or repeated pagination token'
                seen_pages.add(page)
                command = list(command)
                if '--page' in command:
                    index = command.index('--page')
                    command[index + 1] = page
                else:
                    command.extend(['--page', page])
            except Exception as exception:
                return records, f'Search page failed ({type(exception).__name__})'

    def _fetch(self, operation, arguments, region, compartment_id=None, availability_domain=None):
        search = operation == 'search resource structured-search'
        command = ['oci', *operation.split(), *arguments, *([] if search else ['--all']), '--region', region, '--output', 'json']
        error = None
        try:
            if search:
                records, error = self._search_pages(command, operation)
            else:
                records = self._items(self.execute_command(command, operation))
            if records is None:
                error = 'Request failed or response did not contain a resource list'
            elif not self._valid_records(records):
                records = None
                error = 'Response contained invalid resource records'
        except Exception as exception:
            records = None
            error = f'Request failed ({type(exception).__name__})'
        self.coverage.append({
            'operation': operation,
            'region': region,
            'compartment_id': compartment_id,
            'availability_domain': availability_domain,
            'status': 'failed' if records is None or error else ('success' if records else 'empty'),
            'record_count': len(records) if records is not None else None,
            'error': error,
        })
        return records

    @staticmethod
    def _costs(cost_data):
        totals = defaultdict(lambda: defaultdict(float))
        items = cost_data.get('items') if isinstance(cost_data, dict) else None
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            resource_id = item.get('resource-id', item.get('resourceId'))
            region = item.get('region')
            currency = item.get('currency')
            amount = item.get('computed-amount', item.get('computedAmount'))
            if not isinstance(resource_id, str) or not resource_id or not isinstance(currency, str) or not currency or (region is not None and not isinstance(region, str)) or amount is None or isinstance(amount, bool):
                continue
            try:
                value = float(amount)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(value):
                continue
            totals[resource_id, region][currency] += value
        return totals

    def collect_all(self, from_date=None, to_date=None, cost_data=None):
        self.coverage = []
        subscriptions = self._fetch('iam region-subscription list', ['--tenancy-id', self.tenancy_ocid], self.home_region)
        regions = sorted({item['region-name'] for item in subscriptions or []
                          if item.get('region-name') and item.get('status', 'READY') == 'READY'})
        regions_complete = subscriptions is not None and bool(regions)
        if not regions:
            regions = [self.home_region]
        discovered = self._fetch('iam compartment list', [
            '--compartment-id', self.tenancy_ocid, '--compartment-id-in-subtree', 'true',
            '--access-level', 'ANY', '--lifecycle-state', 'ACTIVE'], self.home_region, self.tenancy_ocid)
        compartments = sorted({self.tenancy_ocid, *(item['id'] for item in discovered or []
                              if item.get('id') and item.get('lifecycle-state') == 'ACTIVE')})
        discovery_complete = regions_complete and discovered is not None
        inventory = {name: [] for name in ('resources', 'instances', 'volumes', 'volume_attachments', 'boot_volumes', 'boot_volume_attachments')}
        availability_domains = {}
        candidates = []
        costs = self._costs(cost_data)
        seen = set()

        def store(kind, records, region, compartment=None, ad=None):
            for record in records or []:
                resource_id = record.get('id', record.get('identifier'))
                key = (kind, region, resource_id) if resource_id else (kind, region, compartment, ad, json.dumps(record, sort_keys=True))
                if key in seen:
                    continue
                seen.add(key)
                inventory[kind].append({'region': region, 'compartment_id': compartment or record.get('compartment-id'),
                                        'availability_domain': ad, 'record': record})

        for region in regions:
            resources = self._fetch('search resource structured-search', ['--query-text', 'query all resources'], region)
            store('resources', resources, region)
            ads = self._fetch('iam availability-domain list', ['--compartment-id', self.tenancy_ocid], region, self.tenancy_ocid)
            availability_domains[region] = ads
            block_complete = discovery_complete
            boot_complete = discovery_complete and ads is not None and bool(ads)
            for compartment in compartments:
                arguments = ['--compartment-id', compartment]
                for kind, operation in (
                        ('instances', 'compute instance list'), ('volumes', 'bv volume list'),
                        ('volume_attachments', 'compute volume-attachment list')):
                    records = self._fetch(operation, arguments, region, compartment)
                    store(kind, records, region, compartment)
                    if kind == 'volume_attachments' and records is None:
                        block_complete = False
                    if kind == 'volume_attachments' and any(not record.get('volume-id') and record.get('lifecycle-state') != 'DETACHED' for record in records or []):
                        block_complete = False
                for ad in ads or []:
                    name = ad.get('name')
                    if not name:
                        boot_complete = False
                        continue
                    for kind, operation in (('boot_volumes', 'bv boot-volume list'),
                                            ('boot_volume_attachments', 'compute boot-volume-attachment list')):
                        records = self._fetch(operation, [*arguments, '--availability-domain', name], region, compartment, name)
                        store(kind, records, region, compartment, name)
                        if kind == 'boot_volume_attachments' and records is None:
                            boot_complete = False
                        if kind == 'boot_volume_attachments' and any(not record.get('boot-volume-id') and record.get('lifecycle-state') != 'DETACHED' for record in records or []):
                            boot_complete = False

            attached = {item['record'].get('volume-id') for item in inventory['volume_attachments']
                        if item['region'] == region and item['record'].get('lifecycle-state') != 'DETACHED'}
            boot_attached = {item['record'].get('boot-volume-id') for item in inventory['boot_volume_attachments']
                             if item['region'] == region and item['record'].get('lifecycle-state') != 'DETACHED'}
            for kind, resource_type, complete, attachments in (
                    ('instances', 'instance', True, set()), ('volumes', 'volume', block_complete, attached),
                    ('boot_volumes', 'boot_volume', boot_complete, boot_attached)):
                for item in inventory[kind]:
                    record = item['record']
                    resource_id = record.get('id')
                    if item['region'] != region or not resource_id:
                        continue
                    if kind == 'instances':
                        if record.get('lifecycle-state') != 'STOPPED':
                            continue
                        reason = 'stopped_instance_review'
                    else:
                        if not complete or record.get('lifecycle-state') != 'AVAILABLE' or resource_id in attachments:
                            continue
                        reason = 'unattached_volume_review'
                    resource_costs = defaultdict(float)
                    for key in ((resource_id, None), (resource_id, region)):
                        for currency, amount in costs.get(key, {}).items():
                            resource_costs[currency] += amount
                    candidates.append({
                        'resource_id': resource_id, 'resource_type': resource_type, 'region': region,
                        'compartment_id': item['compartment_id'], 'display_name': record.get('display-name'),
                        'reason': reason, 'lifecycle_state': record.get('lifecycle-state'),
                        'cost_status': 'known' if resource_costs else 'unknown',
                        'costs': [{'currency': currency, 'computed_amount': amount} for currency, amount in sorted(resource_costs.items())],
                        'evidence': 'inventory and complete regional attachment scans' if kind != 'instances' else 'stopped state; billing depends on shape and associated resources',
                    })
        results = {
            'collection_timestamp': datetime.now(timezone.utc).isoformat(),
            'tenancy_ocid': self.tenancy_ocid, 'regions': regions, 'compartments': compartments,
            'discovery_complete': discovery_complete, 'inventory': inventory, 'coverage': self.coverage,
            'discovery': {'region_subscriptions': subscriptions, 'compartments': discovered,
                          'availability_domains': availability_domains},
            'candidates': candidates, 'cost_window': {'from_date': from_date, 'to_date': to_date},
            'cost_data': cost_data if isinstance(cost_data, dict) else None,
            'scope': 'Read-only review candidates; actual costs are not estimated savings. Search includes indexed, authorized resources only.',
        }
        self._save(results)
        return results

    def _save(self, results):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'finops_collection.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        fields = ['resource_id', 'resource_type', 'region', 'compartment_id', 'display_name', 'reason', 'lifecycle_state', 'cost_status', 'costs', 'evidence']
        with (self.output_dir / 'finops_candidates.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for candidate in results['candidates']:
                writer.writerow({**candidate, 'costs': json.dumps(candidate['costs'])})
        failed = sum(item['status'] == 'failed' for item in results['coverage'])
        summary = (f"FinOps collection: {len(results['regions'])} regions; {len(results['compartments'])} compartments\n"
                   f"Review candidates: {len(results['candidates'])}\nFailed collection requests: {failed}\n"
                   f"Discovery complete: {results['discovery_complete']}\n{results['scope']}\n")
        (self.output_dir / 'finops_summary.txt').write_text(summary, encoding='utf-8')
