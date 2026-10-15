"""Within-file charge identity and conservative full reversal matching.

No fuzzy charge synonyms, currency conversion or cross-invoice history.
Amounts are compared exactly as Decimal values, never rounded into a match.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import pandas as pd


def _text(value):
    if pd.isna(value):
        return None
    text = ' '.join(str(value).strip().split()).upper()
    return text or None


def _amount(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def analyze_charges(invoice):
    """Return new matching columns without changing source columns or index.

    Full credits are matched only in one-to-one groups with complete identity.
    Matching across different invoice references is not attempted. A missing
    invoice reference is permitted only when the whole file lacks that column.
    """
    result = invoice.copy()
    n = len(result)
    ids = result['Invoice Line ID'].tolist() if 'Invoice Line ID' in result else list(range(1, n + 1))
    if any(pd.isna(v) for v in ids) or len(set(ids)) != n:
        raise ValueError('Invoice Line ID must be unique and non-missing.')
    typed = 'Charge Type' in result
    values = {name: result[name].tolist() if name in result else [None] * n
              for name in ('AWB', 'Carrier', 'Currency', 'Charge Type', 'Invoice Ref', 'Total')}
    text = {name: [_text(v) for v in vals] for name, vals in values.items() if name != 'Total'}
    amounts = [_amount(v) for v in values['Total']]
    statuses = ['Not a Credit'] * n
    partners = [None] * n
    excluded = [False] * n
    groups = defaultdict(lambda: {'positive': [], 'negative': []})
    for i, amount in enumerate(amounts):
        key = tuple(text[name][i] for name in ('AWB', 'Carrier', 'Currency', 'Charge Type'))
        if 'Invoice Ref' in result:
            key += (text['Invoice Ref'][i],)
        if 'Service Type' in result:
            key += (_text(result['Service Type'].iloc[i]),)
        for component in ('Base Freight', 'Surcharge Amount', 'Tax Amount'):
            if component in result:
                value = _amount(result[component].iloc[i])
                key += (abs(value) if value is not None else None,)
        if amount is None or amount == 0:
            continue
        if any(v is None for v in key):
            if amount < 0:
                statuses[i] = 'Missing Match Information'
            continue
        groups[(key, abs(amount))]['negative' if amount < 0 else 'positive'].append(i)
    for group in groups.values():
        positives, negatives = group['positive'], group['negative']
        if len(positives) == len(negatives) == 1:
            p, c = positives[0], negatives[0]
            statuses[p], statuses[c] = 'Fully Reversed', 'Matched Full Reversal'
            partners[p], partners[c] = ids[c], ids[p]
            excluded[p] = excluded[c] = True
        elif negatives:
            status = 'Ambiguous Credit' if positives else 'Unmatched Credit'
            for c in negatives:
                statuses[c] = status

    exact = [False] * n
    review = [False] * n
    missing_type = [False] * n
    bases = ['Charge type, carrier, AWB, currency and amount' if typed
             else 'Legacy: charge type unavailable'] * n
    seen_exact = set()
    seen_charge = set()
    seen_identity = set()
    incomplete_identities = set()
    for i, amount in enumerate(amounts):
        if amount is None or amount <= 0 or excluded[i]:
            continue
        # Legacy files retain the old positive duplicate key. If a currency
        # column exists, it must also agree. Missing typed keys never match.
        identity = (text['AWB'][i], text['Carrier'][i])
        if typed or 'Currency' in result:
            identity += (text['Currency'][i],)
        if typed:
            charge = identity + (text['Charge Type'][i],)
            incomplete = any(v is None for v in charge)
            missing_type[i] = text['Charge Type'][i] is None
            if incomplete:
                bases[i] = 'Incomplete charge identity - review'
                review[i] = identity in seen_identity
                incomplete_identities.add(identity)
            else:
                exact_key = charge + (amount,)
                exact[i] = exact_key in seen_exact
                review[i] = charge in seen_charge or identity in incomplete_identities
                seen_exact.add(exact_key)
                seen_charge.add(charge)
        else:
            exact_key = identity + (amount,)
            exact[i] = exact_key in seen_exact
            seen_exact.add(exact_key)
        seen_identity.add(identity)

    result['Credit Match Status'] = statuses
    result['Matched Line ID'] = pd.Series(partners, index=result.index, dtype=object)
    result['Excluded From Exposure'] = excluded
    result['Duplicate Match Basis'] = bases
    result['Missing Charge Type'] = missing_type
    result['Needs Charge Review'] = review
    result['Is Exact Duplicate Charge'] = exact
    return result


def apply_charge_rate_scope(results):
    """Do not price credits, cancelled charges or explicit accessorials as freight.

    Only explicit FREIGHT rows use the existing freight-rate check. Files
    without a Charge Type column retain their original rate-check behaviour.
    """
    if 'Charge Type' not in results:
        return results
    result = analyze_charges(results)
    amounts = pd.to_numeric(result['Total'], errors='coerce')
    charge_types = result['Charge Type'].map(_text)
    scope = pd.Series('Freight', index=result.index, dtype=object)
    scope.loc[charge_types.ne('FREIGHT')] = 'Not Assessed - Non Freight'
    scope.loc[charge_types.isna()] = 'Missing Charge Type'
    scope.loc[amounts.eq(0)] = 'Zero-Value Adjustment'
    scope.loc[result['Credit Match Status'].eq('Fully Reversed')] = 'Fully Reversed Charge'
    scope.loc[amounts.lt(0)] = 'Credit or Reversal'
    skip = scope.ne('Freight')
    result.loc[skip, 'Rate Status'] = scope.loc[skip]
    result.loc[skip, 'Rate Difference'] = float('nan')
    if 'Has Missing Base Freight' in result:
        result.loc[skip, 'Has Missing Base Freight'] = False
    result.loc[skip, 'Potential Rate Overcharge'] = float('nan')
    zero = scope.isin(['Fully Reversed Charge', 'Credit or Reversal', 'Zero-Value Adjustment'])
    result.loc[zero, 'Potential Rate Overcharge'] = 0.0
    return result
