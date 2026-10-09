"""Format monetary exports without changing analytical or raw source data."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd


MONEY_COLUMNS = ('computedAmount', 'computed-amount', 'attributedCost',
                 'attributed-cost', 'computed_amount', 'observed_cost', 'unitPrice')


def format_amount(value):
    """Use decimal rounding for display; unavailable amounts stay blank."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return ''
        return format(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
    except (InvalidOperation, ValueError, TypeError):
        return ''


def write_cost_csv(frame, path, *, mode='w', header=True, fieldnames=None):
    """Write only money columns to two decimals and retain source currency."""
    exported = frame.copy()
    columns = [column for column in MONEY_COLUMNS if column in exported]
    for column in columns:
        exported[column] = exported[column].map(format_amount)
    if columns:
        if 'currency' not in exported:
            exported['currency'] = 'Unknown'
        else:
            exported['currency'] = exported['currency'].replace('', pd.NA).fillna('Unknown')
    if fieldnames is not None:
        exported = exported.reindex(columns=fieldnames)
    exported.to_csv(path, index=False, mode=mode, header=header)
