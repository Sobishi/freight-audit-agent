# Freight Audit Agent

A Python-based freight invoice auditing application for identifying billing exceptions,
reconciling carrier charges against supporting evidence, and supporting payment review.

## Capabilities

- Import CSV and Excel carrier invoices.
- Normalize carrier-specific invoice formats using YAML mappings.
- Detect potential duplicate charges, credits, reversals and adjustments.
- Validate freight rates and contract-based pricing when evidence is available.
- Check weight, delivery evidence, surcharges and taxes.
- Reconcile potential financial exposure.
- Generate line-level payment treatments and completeness indicators.
- Export Excel reports and local audit run logs.

## Requirements

- Python 3.12
- Dependencies listed in `requirements.txt`

## Installation

Clone the repository:

    git clone https://github.com/Sobishi/freight-audit-agent.git
    cd freight-audit-agent

Create and activate a virtual environment on macOS or Linux:

    python3.12 -m venv .venv
    source .venv/bin/activate

Install dependencies:

    python -m pip install -r requirements.txt

## Quick start

Run the included Swiftline demonstration invoice:

    python main.py tests/fixtures/carriers/swiftline_invoice.csv --carrier swiftline --output pilot_audit.xlsx

This command was verified during R7.5 pilot documentation testing.

The demonstration processed three invoice lines and generated:

- Audit Summary
- Audit Findings
- Invoice Data
- Final Payment Decisions

A local JSON audit run log is also generated.

### Important payment safeguard

The verified demonstration classified three lines as `Proceed` with `Partial`
decision completeness. These classifications are NOT payment approval.

Missing validation evidence must be investigated before payment.

## Carrier configuration

Carrier profiles are stored in `config/carriers/`.
Invoice mappings are stored in `config/mappings/`.

Included example carrier IDs:

- `swiftline`
- `corvant`
- `northbridge_express`

Example configurations contain illustrative values. Verify contractual
terms and invoice mappings before processing real carrier invoices.

See [Adding a carrier](docs/adding_a_carrier.md).

## CLI options

The CLI accepts a CSV or Excel invoice and optional evidence inputs.

| Option | Purpose |
|---|---|
| `--carrier` | Select a carrier profile and mapping |
| `--output` | Specify the Excel report destination |
| `--rates` | Provide agreed carrier rates |
| `--contract-rates` | Provide a weight-based contract rate card |
| `--delivery-evidence` | Provide delivery tracking or POD evidence |
| `--surcharge-evidence` | Provide surcharge contract evidence |
| `--tax-evidence` | Provide tax contract evidence |
| `--weight-tolerance` | Set an absolute weight tolerance in kilograms |
| `--package-count-verified` | Confirm independently verified package counts |
| `--sheet` | Select an Excel worksheet |
| `--header-row` | Specify the zero-based header row |
| `--config-dir` | Select another carrier configuration directory |
| `--log-dir` | Select the audit log directory |

Run the following command for the full CLI reference:

    python main.py --help

The `--allow-total-fallback` option compares rates against invoice Total
when Base Freight is unavailable. It may overstate overcharges if Total
includes taxes or surcharges.

## Audit interpretation

- Potential duplicates require investigation before making carrier claims.
- Missing evidence is not proof that a charge is correct.
- Unknown financial exposure must not be interpreted as zero liability.
- Payment treatments must be considered alongside decision completeness.
- Failed or incomplete audits must not authorize payment.

The application does not execute carrier payments.

## Data integrity

The application rejects malformed or non-finite invoice financial amounts.
Excel reports are generated using temporary files and atomic replacement
to protect existing reports if generation or replacement fails.

Audit run logs record operational metadata and input hashes.
They are local records, not immutable or tamper-proof audit trails.

See [Rule IDs and run logs](docs/rule_ids_and_run_logs.md).

## Tests

Run the test suite:

    python -m pytest tests/ -q --tb=short

The R7.4 regression baseline passed 1,012 tests.

## Project status

- R1-R6: Core audit and financial-control functionality implemented.
- R7.1-R7.4: Pilot acceptance and integrity checks completed.
- R7.5: Pilot documentation in progress.
- R7.6: Final regression and V1 release preparation pending.

This is a pilot-stage application. Financial conclusions require
appropriate supporting evidence and operational review.
