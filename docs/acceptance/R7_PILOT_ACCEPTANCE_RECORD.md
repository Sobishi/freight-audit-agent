# R7 Pilot Acceptance Record

## Product

Freight Audit and Rate Intelligence Engine

## Release

v0.1.0-engine-pilot

Release commit:
7e09c548a0b07778095f03657667b3abe6038d09

## 1. Engineering validation

Status: Verified

- Full regression: 1,012 tests passed.
- Original private workbook: 1,240 invoice records.
- Workbook duplicate occurrence comparison: passed.
- Expected duplicate count: 14.
- GitHub engineering prerelease: published.

## 2. Controlled technical pilot

Status: Verified

Carrier: Swiftline

Input:
tests/fixtures/carriers/swiftline_invoice.csv

Audit run ID:
077afca8-c6b1-48af-aa87-ae5205d55d9b

Results:

- Execution status: succeeded.
- Execution errors: none.
- Invoice lines: 3.
- Invoice total: USD 1,834.90.
- Audit findings: 0.
- Reported gross potential exposure: USD 0.00.
- Final Payment Treatment: 3 Proceed.
- Decision Completeness: 3 Partial.

## 3. Retained evidence

Local evidence directory:

~/freight-audit-pilot-acceptance/swiftline/

Files:

- swiftline_pilot.xlsx
- logs/audit_077afca8-c6b1-48af-aa87-ae5205d55d9b.json

Verification:

- Report and JSON run IDs match.
- JSON run ID matches log filename.
- Execution status is succeeded.
- JSON error is null.
- Invoice totals and decision classifications verified.

These files are retained locally and are not committed
to the repository.

## 4. Validation limitations

The Swiftline carrier configuration contains illustrative
demonstration values.

The controlled pilot did not independently establish
commercial contract compliance.

The following checks were not run:

- Contract pricing.
- Tax validation.
- Surcharge validation.
- Weight validation.
- Delivery evidence validation.

Duplicate matching used the legacy basis because
charge type information was unavailable.

Zero identified exposure does not establish zero
actual overcharges.

Proceed with Partial completeness does not constitute
authorization to pay.

## 5. Outstanding business acceptance

- Verify carrier mapping against approved commercial terms.
- Supply and independently verify supporting evidence.
- Review incomplete decisions and missing validations.
- Investigate applicable holds, credits and reversals.
- Independently review financial exposure.
- Complete the controlled-pilot defect review.
- Obtain authorized business acceptance and sign-off.

## 6. Acceptance conclusion

Engineering release: COMPLETE.

Controlled technical pilot: VERIFIED.

Operational and commercial pilot acceptance:
OUTSTANDING.

This record supports progression into W1 engineering
development. It does not authorize production use,
payment execution or commercial pilot sign-off.

## 7. Product continuation

W1: Controlled web interface.
W2: Hosted pilot and launch readiness.
B1: Historical audit intelligence.
B2: Cross-carrier rate intelligence.
B3: Operational intelligence.
B4: Carrier, ERP and TMS integrations.
B5: Broader freight modes and currency support.

The full product remains the Freight Audit and
Rate Intelligence Engine.
