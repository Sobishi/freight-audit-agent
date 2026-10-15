import pandas as pd
import pytest
from audit_engine.rules import RULES, get_rule, rule_reference, tag_duplicate_findings, tag_rate_results
from audit_engine.audit import detect_duplicates, detect_exact_duplicate_charges, generate_duplicate_findings
from audit_engine.rate_validation import validate_freight_rates


def test_catalogue_distinguishes_planned_rules():
    assert get_rule('WT-01').status == 'planned'
    assert get_rule('REP-01').status == 'implemented'
    with pytest.raises(ValueError):
        get_rule('UNKNOWN')


def test_duplicate_tags_do_not_change_financial_results():
    raw = pd.DataFrame({'AWB': ['A'] * 5, 'Carrier': ['Demo'] * 5,
                        'Total': [100, 100, 30, -100, 0]})
    audited = detect_exact_duplicate_charges(detect_duplicates(raw))
    findings = generate_duplicate_findings(audited)
    assert findings['Rule ID'].tolist() == ['DUP-01', 'REP-01', 'CR-01', 'ADJ-01']
    assert findings['Potential Exposure'].tolist() == [100, 30, 0, 0]
    assert findings['Rule Version'].notna().all()


def test_empty_findings_keep_traceability_columns():
    findings = generate_duplicate_findings(detect_duplicates(pd.DataFrame({'AWB': ['A'], 'Total': [1]})))
    assert findings.empty
    assert {'Rule ID', 'Rule Version', 'Rule Description'} <= set(findings)


def test_rate_tags_preserve_overlapping_missing_flags():
    raw = pd.DataFrame({'AWB': ['A', 'B', 'C', 'D'], 'Carrier': ['Demo', None, 'Other', 'Demo'],
                        'Service Type': ['Express'] * 4, 'Total': [110, 100, 100, 90],
                        'Base Freight': [110, None, 100, 90]})
    rates = pd.DataFrame({'Carrier': ['Demo'], 'Service Type': ['Express'], 'Agreed Rate': [100]})
    result = validate_freight_rates(raw, rates)
    assert result['Rule IDs'].tolist() == ['RATE-02', 'DATA-02; BASE-01', 'RATE-01', 'UNDER-01']
    assert result.loc[0, 'Potential Rate Overcharge'] == 10
    assert pd.isna(result.loc[1, 'Potential Rate Overcharge'])


def test_taggers_do_not_mutate_input():
    raw = pd.DataFrame({'Rate Status': ['Rate Matched']})
    result = tag_rate_results(raw)
    assert result.loc[0, 'Rule IDs'] == ''
    assert 'Rule IDs' not in raw


def test_planned_rule_cannot_be_attached_to_a_finding():
    with pytest.raises(ValueError, match='planned'):
        rule_reference('WT-01')
