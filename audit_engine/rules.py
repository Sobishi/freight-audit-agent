"""Versioned rule catalogue and traceability tags, not pricing calculations."""
from dataclasses import asdict, dataclass
from types import MappingProxyType
import pandas as pd

CATALOGUE_VERSION = '1.1.0'

@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    status: str = 'implemented'
    version: str = '1.0.0'

RULES = MappingProxyType({r.rule_id: r for r in (
    Rule('REP-01', 'Repeated charge requiring review; not proof of duplicate billing', version='2.0.0'),
    Rule('DUP-01', 'Potential repeated positive charge using charge identity when available; legacy basis labelled', version='2.0.0'),
    Rule('CR-01', 'Negative charge with conservative within-file full reversal matching', version='2.0.0'),
    Rule('CHG-01', 'Missing charge type or incomplete charge identity'),
    Rule('SCOPE-01', 'Explicit non-freight charge not assessed against a freight rate'),
    Rule('ADJ-01', 'Zero-value repeated-AWB adjustment'),
    Rule('DATA-02', 'Missing carrier or service information'),
    Rule('BASE-01', 'Missing base freight amount'),
    Rule('RATE-01', 'Contract rate not found for carrier and service'),
    Rule('RATE-02', 'Billed freight above carrier/service rate, outside tolerance'),
    Rule('UNDER-01', 'Billed freight below carrier/service rate, outside tolerance'),
    Rule('DATA-01', 'Missing internal shipment record', 'planned'),
    Rule('POD-01', 'No proof of delivery', 'planned'),
    Rule('WT-01', 'Billed weight overstated', 'planned'),
    Rule('WT-02', 'Billed weight understated', 'planned'),
    Rule('SUR-01', 'Surcharge outside contract', 'planned'),
    Rule('TAX-01', 'Tax mismatch', 'planned'),
)})

DUPLICATE_RULE_IDS = ('REP-01', 'DUP-01', 'CR-01', 'ADJ-01', 'CHG-01')
RATE_RULE_IDS = ('DATA-02', 'BASE-01', 'RATE-01', 'RATE-02', 'UNDER-01', 'CR-01', 'ADJ-01', 'CHG-01', 'SCOPE-01')


def get_rule(rule_id):
    try:
        return RULES[rule_id]
    except KeyError as error:
        raise ValueError(f'Unknown rule ID: {rule_id}') from error


def rule_reference(rule_id):
    rule = get_rule(rule_id)
    if rule.status != 'implemented':
        raise ValueError(f'{rule_id} is planned, not implemented.')
    return {'rule_id': rule.rule_id, 'version': rule.version}


def catalogue():
    return [asdict(rule) for rule in RULES.values()]


def tag_duplicate_findings(findings):
    result = findings.copy()
    ids = []
    for _, row in result.iterrows():
        classification = row.get('Classification')
        if _flag(row, 'Missing Charge Type'):
            rule_id = 'CHG-01'
        elif classification == 'Credit or Reversal':
            rule_id = 'CR-01'
        elif classification == 'Zero-Value Adjustment':
            rule_id = 'ADJ-01'
        elif pd.notna(row.get('Exact Charge Match')) and bool(row.get('Exact Charge Match')):
            rule_id = 'DUP-01'
        else:
            rule_id = 'REP-01'
        ids.append(rule_id)
    result['Rule ID'] = pd.Series(ids, index=result.index, dtype=object)
    result['Rule Version'] = result['Rule ID'].map(lambda value: get_rule(value).version)
    result['Rule Description'] = result['Rule ID'].map(lambda value: get_rule(value).description)
    return result


def _flag(row, column):
    value = row.get(column, False)
    return bool(value) if pd.notna(value) else False


def tag_rate_results(results):
    result = results.copy()
    tags = []
    for _, row in result.iterrows():
        status = row.get('Rate Status')
        ids = []
        if _flag(row, 'Has Missing Invoice Information') or status == 'Missing Invoice Information':
            ids.append('DATA-02')
        if _flag(row, 'Has Missing Base Freight') or status == 'Missing Base Freight':
            ids.append('BASE-01')
        status_rule = {'Credit or Reversal': 'CR-01', 'Fully Reversed Charge': 'CR-01',
                       'Zero-Value Adjustment': 'ADJ-01', 'Missing Charge Type': 'CHG-01',
                       'Not Assessed - Non Freight': 'SCOPE-01', 'Rate Not Found': 'RATE-01', 'Potential Overcharge': 'RATE-02',
                       'Below Agreed Rate': 'UNDER-01'}.get(status)
        if status_rule:
            ids.append(status_rule)
        tags.append(ids)
    result['Rule IDs'] = pd.Series(['; '.join(ids) for ids in tags], index=result.index, dtype=object)
    result['Rule Versions'] = pd.Series(
        ['; '.join(f'{rid}@{get_rule(rid).version}' for rid in ids) for ids in tags],
        index=result.index, dtype=object)
    result['Rule Descriptions'] = pd.Series(
        ['; '.join(get_rule(rid).description for rid in ids) for ids in tags],
        index=result.index, dtype=object)
    return result
