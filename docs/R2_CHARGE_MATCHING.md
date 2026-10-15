# R2 charge matching

Apply this patch to the completed R1 project. Run each command separately:

```bash
git apply --check phase_r2_charge_matching_fixed.patch
git apply phase_r2_charge_matching_fixed.patch
python -m pytest tests/ -q
```

Typed positive duplicates require matching carrier, AWB, currency, charge type
and exact amount. Different amounts of the same charge type require review.
Files without Charge Type retain labelled legacy matching.

Full reversals require one positive and one negative with complete matching
identity and absolute amount. Invoice Ref, Service Type and freight, surcharge
and tax components must agree when present. Matched pairs are linked and
excluded from exposure. Partial or ambiguous credits remain for review.

Only explicit FREIGHT lines are compared with freight rates. Other charge types
and missing types are not cleared as valid. Unknown exposure is not zero liability.
Use one verified currency per run. Rates still match carrier and service, not
route, zone or currency. There is no currency conversion, cross-file credit
matching, partial-credit allocation or automatic payment action.

Optional mapping example, merge into your existing carrier mapping:

```yaml
columns:
  Charge Code: Charge Type
  Currency Code: Currency
charge_type_aliases:
  TRANSPORT: FREIGHT
  FUEL ADJUSTMENT: FUEL
```

Map codes only after verifying their carrier definitions. Each typed row must
represent one charge. Do not label a shipment total FREIGHT if it includes
other charges. Do not default mixed-currency files to a single currency.

Invoice Data retains source rows and matching columns. Findings, rate results,
exposure reconciliation and run logs carry the new matching information.

This corrected patch is rebuilt against project_bundle_updated 3.txt.
