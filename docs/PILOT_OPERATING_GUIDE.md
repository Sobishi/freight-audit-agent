# Freight Audit Agent: Pilot Operating Guide

## 1. Purpose

This guide explains how to operate the Freight Audit Agent during
the V1 pilot and interpret its financial-control outputs.

The application supports freight invoice validation and payment
review. It does not automatically approve or execute payments.

## 2. Pilot operating principles

1. Preserve the original carrier invoice and supporting evidence.
2. Verify the carrier configuration and applicable contract terms.
3. Use independently verified evidence where available.
4. Investigate exceptions before making carrier claims.
5. Do not interpret missing validation as a passed check.
6. Do not interpret unknown financial exposure as zero liability.
7. Keep audit reports and run logs available for review.
8. Apply organizational payment approval controls separately.

## 3. Prepare the audit inputs

### 3.1 Carrier invoice

Obtain the original carrier invoice in CSV or Excel format.

Confirm the relevant carrier, invoice period, currency,
shipment identifiers and financial amounts.

Check that the invoice has the fields required by the
applicable carrier mapping.

### 3.2 Carrier configuration

Carrier profiles are stored in `config/carriers/`.
Invoice mappings are stored in `config/mappings/`.

Verify that the selected carrier ID matches both files.
Check column mappings, currency assumptions and contract terms.

The bundled carrier configurations use illustrative values.
They must not be treated as verified commercial agreements.

See [Adding a carrier](adding_a_carrier.md).

### 3.3 Supporting evidence

Collect relevant supporting documents where available:

- Agreed carrier rates.
- Weight-based contract rate cards.
- Delivery tracking and proof-of-delivery records.
- Surcharge contract evidence.
- Tax contract evidence.
- Independently verified shipment weight or package information.

Only use evidence that applies to the relevant carrier,
shipment, service and contract period.

## 4. Run an audit

Activate the project's Python environment:

    source .venv/bin/activate

A verified demonstration command is:

    python main.py tests/fixtures/carriers/swiftline_invoice.csv --carrier swiftline --output pilot_audit.xlsx

For an actual carrier invoice, supply its file path,
the correct carrier ID and a report destination.

Example:

    python main.py invoice.xlsx --carrier swiftline --output audit_report.xlsx

This example assumes the invoice matches the Swiftline
configuration. Do not use that mapping for unrelated carriers.

### 4.1 Optional evidence arguments

| Argument | Evidence |
|---|---|
| `--rates` | Agreed carrier/service rates |
| `--contract-rates` | Weight-based freight contract rates |
| `--delivery-evidence` | Tracking or proof-of-delivery workbook |
| `--surcharge-evidence` | Invoice-line surcharge terms |
| `--tax-evidence` | Invoice-line tax terms |
| `--weight-tolerance` | Absolute weight tolerance in kilograms |
| `--package-count-verified` | Independent package-count confirmation |

Use `python main.py --help` for all supported options.

The `--allow-total-fallback` option requires particular care.
Comparing against invoice Total can overstate freight
overcharges when Total includes tax or surcharges.

## 5. Confirm successful execution

A successful CLI run produces an Excel audit report and
a local JSON audit run log.

The terminal prints the report destination, audit summary
and audit run identifier.

Before reviewing payment decisions:

1. Confirm the command completed successfully.
2. Confirm the expected invoice was processed.
3. Confirm the Excel report can be opened.
4. Locate the corresponding audit run log.
5. Confirm that required evidence was actually supplied.

A failed or incomplete run must not be treated as a
successful audit.

## 6. Review the Excel report

### 6.1 Core worksheets

| Worksheet | Review purpose |
|---|---|
| Audit Summary | Review overall audit results and run identity |
| Audit Findings | Investigate recorded exceptions |
| Invoice Data | Trace findings to invoice lines |
| Final Payment Decisions | Review treatment, completeness and reasons |

### 6.2 Additional worksheets

Depending on supplied evidence, the report may also include:

- Rate Validation
- Weight Validation
- Contract Pricing
- Delivery Evidence
- Surcharge Validation
- Tax Validation
- Exposure Reconciliation

An absent validation worksheet must not be interpreted
as confirmation that the relevant checks passed.

## 7. Interpret final payment decisions

The final decision engine produces three important fields:

- `Final Payment Treatment`
- `Decision Completeness`
- `Decision Reason`

### 7.1 Final Payment Treatment

| Treatment | Operational interpretation |
|---|---|
| `Proceed` | Available checks did not identify a hold condition |
| `Hold` | One or more conditions require investigation |
| `Review Credit` | Unresolved credit or negative amount needs review |
| `No Payment - Reversed` | Qualifying matched reversal is excluded |
| `No Payment - Zero` | Zero-value line requires no payment |

These are application classifications, not final
authorization to pay a carrier.

### 7.2 Decision Completeness

`Complete` means all validation result frames expected
by the final decision function are present.

`Partial` means at least one such result frame is missing.

Completeness is independent of payment treatment.

A `Complete` decision can still have a `Hold` treatment.
A `Partial` decision can have a `Proceed` treatment.

Neither condition alone constitutes payment approval.

### 7.3 Decision Reason

Review the `Decision Reason` field for the specific
conditions supporting the classification.

Examples of conditions assessed by the engine include:

- Potential duplicate charges or charge-review flags.
- Unresolved credits or inconsistent reversal information.
- Potential contract, surcharge or tax overcharges.
- Unknown or invalid financial exposure.
- Weight discrepancies.
- Delivery status not confirmed.
- Preliminary payment review requirements.

Do not override these findings without documented
investigation and appropriate approval.

## 8. Investigate exceptions

For each line requiring investigation:

1. Identify its invoice line and shipment reference.
2. Review the corresponding audit finding and decision reason.
3. Compare the carrier invoice with source records.
4. Verify the applicable contract or rate terms.
5. Obtain missing evidence or clarify disputed charges.
6. Document the conclusion and supporting evidence.
7. Rerun the audit when corrected inputs are available.

Potential duplicate findings are not automatically
confirmed duplicate-billing claims.

Unmatched or ambiguous credits must not be assumed
to offset an original invoice charge.

## 9. Interpret financial exposure

The application distinguishes quantified potential
exposure from exposure that cannot be determined.

A numeric zero used for an unknown exposure must not
be interpreted as proof that there is no liability.

Review the applicable exposure status alongside
the financial amount.

Contract pricing, surcharge and tax results may appear
in separate worksheets and should not be added blindly
to other exposure totals.

Do not aggregate different currencies as though
they were a single currency.

## 10. Payment review and release controls

Before authorizing payment through the organization's
normal financial process:

1. Confirm the audit completed successfully.
2. Review every `Hold` and `Review Credit` classification.
3. Confirm how missing validation evidence was addressed.
4. Reconcile invoice totals and relevant credits.
5. Review potential financial exposure and its status.
6. Confirm that contractual disputes are resolved or documented.
7. Obtain approval from the authorized payment reviewer.

A `Proceed` treatment with `Partial` completeness
must not be interpreted as payment approval.

Even when completeness is `Complete`, independent
organizational payment authorization is still required.

The application does not execute payments.

## 11. Failed runs and data integrity

Stop the payment review if the audit fails or its
input-integrity checks identify changed source files.

Do not use a failed run's output as a valid audit result.

Correct the underlying issue and perform a fresh run.

Report generation uses temporary files and atomic
replacement to protect existing Excel reports.

Keep original invoices and evidence unchanged during
processing.

## 12. Audit logs and record retention

CLI runs produce local JSON audit records containing
execution metadata, input hashes and rule traceability.

The records are not immutable or tamper-proof.

Store invoices, evidence, reports and logs in an
appropriately restricted location.

Apply the organization's record retention requirements.

See [Rule IDs and run logs](rule_ids_and_run_logs.md).

## 13. Pilot acceptance checklist

- [ ] Correct carrier and invoice selected.
- [ ] Carrier mapping and contract terms verified.
- [ ] Supporting evidence identified and supplied.
- [ ] Audit completed successfully.
- [ ] Excel report and run log available.
- [ ] Findings and payment decisions reviewed.
- [ ] Partial decisions and missing evidence addressed.
- [ ] Holds, credits and reversals investigated.
- [ ] Financial exposure reviewed without double counting.
- [ ] Payment authorization handled outside the application.

## 14. Known pilot limitations

- The application is currently a command-line pilot.
- Bundled carrier configurations contain illustrative values.
- Validation coverage depends on the supplied evidence.
- Missing evidence does not constitute a passed check.
- The application does not automatically execute payments.
- Local audit logs are not immutable records.

This guide documents the V1 pilot workflow and does
not replace carrier contracts or financial approval policies.
