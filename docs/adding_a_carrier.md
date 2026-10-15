# Adding a carrier

A new carrier needs two small files and no code changes.

| File | Purpose |
|---|---|
| `config/carriers/<carrier_id>.yaml` | The carrier's contract rules (the profile) |
| `config/mappings/<carrier_id>_invoice.yaml` | How the carrier's invoice columns map to the standard format |

The carrier id uses lowercase letters, numbers and underscores, for example `acme_air`.
Both files must declare the same `carrier_id`.

## 1. The profile

```yaml
carrier_id: acme_air
carrier_name: Acme Air
currency: USD
pricing_method: parcel_zone_weight
unit_system: metric            # metric or imperial
dim_divisor: 5000              # cubic cm per kg
rounding:                      # round up to the next 0.5 kg to 10 kg, then the next 1 kg
  step_low: 0.5
  threshold: 10
  step_high: 1
tolerance: 0.01                # largest difference still treated as a match
```

Optional settings: `max_band`, `excess_band_code`, `tax_rate`, `tax_inclusive`,
`surcharge_basis` (`per_kg`, `fixed` or `percent_of_freight`), `valid_from`, `valid_to`.

Today only `tolerance` changes the audit result. The other settings are validated and
stored now, and the pricing engine uses them in a later phase.

The profiles in `config/carriers/` use illustrative values. Replace them with the terms in
your own contract before using them on real invoices.

## 2. The mapping

```yaml
carrier_id: acme_air
carrier_name: Acme Air
header_row: 0                  # the line holding the column names, counting from 0
date_format: "%d/%m/%Y"        # only needed if the carrier does not write YYYY-MM-DD
columns:
  "Consignment": AWB           # carrier column name -> standard field
  "Freight": Base Freight
  "Net": Total
```

`AWB` and `Total` must be mapped. The other standard fields are:

`Alt AWB`, `Carrier`, `Invoice Ref`, `Invoice Date`, `Ship Date`, `Service Type`, `Charge Type`,
`Billed Zone`, `Origin City`, `Origin Country`, `Destination City`, `Destination Country`,
`Pieces`, `Billed Weight`, `Weight Unit`, `Base Freight`, `Surcharge Amount`, `Tax Amount`,
`Currency`.

Other mapping settings:

| Setting | Use |
|---|---|
| `sheet` | Worksheet name for Excel files |
| `decimal`, `thousands` | Number format, for example `decimal: ","` and `thousands: "."` |
| `defaults` | A fixed value for a field the file lacks, for example `Origin Country: "GB"` |

Notes:

- Column names are matched ignoring case, spaces and punctuation.
- Currency and weight unit come from the profile unless the mapping sets them.
- Put text defaults in quotes. YAML reads `NO` and `yes` as true and false.
- If the carrier changes a column name, the run stops and names the missing column.
- Without `date_format`, only `YYYY-MM-DD` dates are accepted. A day first date is never
  silently read month first.

## 3. Run it

```
python main.py invoice.xlsx --carrier acme_air --rates rates.csv
```

Use `--config-dir` to read the config files from another folder.
