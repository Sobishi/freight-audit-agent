import pandas as pd
import pytest
from audit_engine.audit import detect_duplicates, detect_exact_duplicate_charges, generate_duplicate_findings
from audit_engine.charges import analyze_charges
from audit_engine.rate_validation import validate_freight_rates
from audit_engine.exposure import calculate_combined_exposure


def invoice(amounts, types=None, **overrides):
    n = len(amounts)
    data = {'Invoice Line ID': list(range(1, n+1)), 'AWB': ['A']*n,
            'Carrier': ['Demo']*n, 'Currency': ['USD']*n, 'Total': amounts,
            'Service Type': ['Express']*n, 'Base Freight': amounts}
    if types is not None:
        data['Charge Type'] = types
    data.update(overrides)
    return pd.DataFrame(data)


def audit(raw):
    return detect_exact_duplicate_charges(detect_duplicates(raw))


def test_different_charge_types_are_not_duplicates_even_with_same_amount():
    data = audit(invoice([100,100], ['FREIGHT','FUEL']))
    assert data['Is Exact Duplicate Charge'].tolist() == [False,False]
    assert generate_duplicate_findings(data).empty


def test_same_charge_type_and_amount_flags_second_only():
    data = audit(invoice([100,100], ['FREIGHT',' freight ']))
    assert data['Is Exact Duplicate Charge'].tolist() == [False,True]
    assert generate_duplicate_findings(data)['Potential Exposure'].tolist() == [100]


def test_different_currencies_do_not_match():
    data = audit(invoice([100,100], ['FREIGHT']*2, Currency=['USD','EUR']))
    assert not data['Is Exact Duplicate Charge'].any()
    assert generate_duplicate_findings(data).empty


def test_different_carriers_do_not_match():
    data = audit(invoice([100,100], ['FREIGHT']*2, Carrier=['Demo','Other']))
    assert not data['Is Exact Duplicate Charge'].any()
    assert generate_duplicate_findings(data).empty


@pytest.mark.parametrize('types', [['FREIGHT',None], [None,None], ['',' ']])
def test_missing_charge_type_is_review_not_exact(types):
    data = audit(invoice([100,100], types))
    assert not data['Is Exact Duplicate Charge'].any()
    findings = generate_duplicate_findings(data)
    assert len(findings) == 1
    assert findings['Potential Exposure'].isna().all()
    assert findings['Rule ID'].eq('CHG-01').all()


def test_same_type_different_amount_is_review_not_full_claim():
    findings = generate_duplicate_findings(audit(invoice([100,120], ['FREIGHT']*2)))
    assert len(findings) == 1
    assert pd.isna(findings.iloc[0]['Potential Exposure'])
    assert findings.iloc[0]['Rule ID'] == 'REP-01'


def test_legacy_no_charge_column_retains_compatibility_but_labels_limit():
    data = audit(invoice([100,100]))
    assert data['Is Exact Duplicate Charge'].tolist() == [False,True]
    assert data['Duplicate Match Basis'].eq('Legacy: charge type unavailable').all()


def test_unique_full_credit_pairs_both_rows():
    data = analyze_charges(invoice([100,-100], ['FREIGHT']*2))
    assert data['Credit Match Status'].tolist() == ['Fully Reversed','Matched Full Reversal']
    assert data['Matched Line ID'].tolist() == [2,1]
    assert data['Excluded From Exposure'].all()


def test_credit_before_positive_is_supported():
    data = analyze_charges(invoice([-100,100], ['FREIGHT']*2))
    assert data['Credit Match Status'].tolist() == ['Matched Full Reversal','Fully Reversed']


def test_rebill_after_unique_reversal_is_not_duplicate():
    data = audit(invoice([100,-100,110], ['FREIGHT']*3))
    assert not data['Is Exact Duplicate Charge'].any()
    assert generate_duplicate_findings(data)['Classification'].tolist() == ['Credit or Reversal']


def test_ambiguous_credit_does_not_reduce_exposure():
    data = audit(invoice([100,100,-100], ['FREIGHT']*3))
    assert data.loc[2,'Credit Match Status'] == 'Ambiguous Credit'
    assert not data['Excluded From Exposure'].any()
    assert data['Is Exact Duplicate Charge'].tolist() == [False,True,False]


def test_multiple_credits_for_one_positive_are_ambiguous():
    data = analyze_charges(invoice([100,-100,-100], ['FREIGHT']*3))
    assert data['Credit Match Status'].tolist() == ['Not a Credit','Ambiguous Credit','Ambiguous Credit']


@pytest.mark.parametrize('amount',[-20,-150])
def test_partial_or_excess_credit_is_unmatched(amount):
    data = analyze_charges(invoice([100,amount], ['FREIGHT']*2))
    assert data.loc[1,'Credit Match Status'] == 'Unmatched Credit'
    assert not data['Excluded From Exposure'].any()


@pytest.mark.parametrize('field,values',[
    ('Currency',['USD','EUR']),('Charge Type',['FREIGHT','FUEL']),
    ('Carrier',['Demo','Other']),('AWB',['A','B'])])
def test_credit_cannot_cross_identity_boundaries(field,values):
    data = analyze_charges(invoice([100,-100], ['FREIGHT']*2, **{field:values}))
    assert data.loc[1,'Credit Match Status'] == 'Unmatched Credit'


@pytest.mark.parametrize('field',['Currency','Charge Type','Carrier'])
def test_credit_with_missing_key_is_not_automatically_matched(field):
    data = analyze_charges(invoice([100,-100], ['FREIGHT']*2).drop(columns=[field]))
    assert data.loc[1,'Credit Match Status'] == 'Missing Match Information'


def test_one_credit_is_still_reported_without_repeated_awb():
    findings = generate_duplicate_findings(audit(invoice([-100], ['FREIGHT'])))
    assert findings['Classification'].tolist() == ['Credit or Reversal']


def test_matched_reversal_is_removed_from_rate_and_combined_exposure():
    raw = invoice([110,-110], ['FREIGHT']*2)
    rates = pd.DataFrame({'Carrier':['Demo'],'Service Type':['Express'],'Agreed Rate':[100]})
    results = validate_freight_rates(raw,rates)
    assert results['Potential Rate Overcharge'].tolist() == [0,0]
    assert results['Rate Status'].tolist() == ['Fully Reversed Charge','Credit or Reversal']
    combined = calculate_combined_exposure(audit(raw),results)
    assert combined['Combined Potential Exposure'].tolist() == [0,0]
    assert combined['Payment Treatment'].eq('No Payment - Reversed').all()


def test_unmatched_credit_is_not_an_undercharge():
    raw = invoice([-20], ['FREIGHT'])
    rates = pd.DataFrame({'Carrier':['Demo'],'Service Type':['Express'],'Agreed Rate':[100]})
    result = validate_freight_rates(raw,rates)
    assert result.loc[0,'Rate Status'] == 'Credit or Reversal'
    assert result.loc[0,'Potential Rate Overcharge'] == 0


def test_non_freight_charge_is_not_compared_with_freight_rate():
    raw = invoice([30], ['FUEL'])
    rates = pd.DataFrame({'Carrier':['Demo'],'Service Type':['Express'],'Agreed Rate':[10]})
    result = validate_freight_rates(raw,rates)
    assert result.loc[0,'Rate Status'] == 'Not Assessed - Non Freight'
    assert pd.isna(result.loc[0,'Potential Rate Overcharge'])


def test_inputs_and_nondefault_index_are_preserved():
    raw = invoice([100,-100], ['FREIGHT']*2)
    raw.index = [7,3]
    before = raw.copy(deep=True)
    result = analyze_charges(raw)
    pd.testing.assert_frame_equal(raw,before)
    assert result.index.tolist() == [7,3]
    assert result['Matched Line ID'].tolist() == [2,1]


def test_no_rounding_into_false_full_credit():
    data = analyze_charges(invoice([100,-100.001], ['FREIGHT']*2))
    assert data.loc[1,'Credit Match Status'] == 'Unmatched Credit'


def test_duplicate_line_ids_are_rejected():
    with pytest.raises(ValueError,match='unique'):
        analyze_charges(invoice([100,-100], ['FREIGHT']*2, **{'Invoice Line ID':[1,1]}))


def test_missing_type_on_first_row_still_triggers_review_on_second():
    findings = generate_duplicate_findings(audit(invoice([100,100], [None,'FREIGHT'])))
    assert len(findings) == 1
    assert findings['Potential Exposure'].isna().all()


def test_typed_rows_without_currency_do_not_match_as_exact():
    data = audit(invoice([100,100], ['FREIGHT']*2).drop(columns=['Currency']))
    assert not data['Is Exact Duplicate Charge'].any()
    assert data.loc[1,'Needs Charge Review']


def test_full_credit_cannot_cross_invoice_references():
    data = analyze_charges(invoice([100,-100], ['FREIGHT']*2, **{'Invoice Ref':['I1','I2']}))
    assert data.loc[1,'Credit Match Status'] == 'Unmatched Credit'


def test_equal_total_but_different_freight_components_is_not_full_reversal():
    data = analyze_charges(invoice([100,-100], ['FREIGHT']*2, **{'Base Freight':[90,-80]}))
    assert not data['Excluded From Exposure'].any()


def test_charge_review_is_held_in_combined_exposure():
    raw = invoice([100,120], ['FREIGHT']*2)
    rates = pd.DataFrame({'Carrier':['Demo'],'Service Type':['Express'],'Agreed Rate':[120]})
    combined = calculate_combined_exposure(audit(raw),validate_freight_rates(raw,rates))
    assert combined.loc[1,'Payment Treatment'] == 'Hold'
    assert combined.loc[1,'Duplicate Exposure Status'] == 'Unknown'


def test_mapping_aliases_are_configuration_not_hardcoded_carrier_logic():
    from data.mapping import parse_mapping, standardize_invoice
    mapping = parse_mapping({'carrier_id':'demo','carrier_name':'Demo',
        'columns':{'Waybill':'AWB','Gross':'Total','Code':'Charge Type'},
        'charge_type_aliases':{'transport':'FREIGHT','fuel adjustment':'FUEL'}})
    raw = pd.DataFrame({'Waybill':['A','A'],'Gross':[100,10],'Code':[' TRANSPORT ','Fuel Adjustment']})
    assert standardize_invoice(raw,mapping)['Charge Type'].tolist() == ['FREIGHT','FUEL']


@pytest.mark.parametrize('bad',[[],{'x':None},{'x':True},{'x':'FREIGHT',' X ':'FUEL'}])
def test_invalid_charge_aliases_are_rejected(bad):
    from data.mapping import parse_mapping
    with pytest.raises(ValueError,match='charge_type_aliases'):
        parse_mapping({'carrier_id':'demo','carrier_name':'Demo',
            'columns':{'Waybill':'AWB','Gross':'Total'},'charge_type_aliases':bad})
