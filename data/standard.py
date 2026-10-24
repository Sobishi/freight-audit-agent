"""
The standard invoice format.

Every carrier invoice is converted into these fields, whatever the
carrier calls its columns. The rest of the engine only ever sees
standard field names.

Fields marked "lane" are captured now so that rate comparison can be
added later without changing the data model. They are not used yet.
"""

TEXT = "text"
NUMBER = "number"
DATE = "date"

# Standard field name -> data type, in the order they appear in the output.
STANDARD_INVOICE_FIELDS = {
    "AWB": TEXT,
    "Alt AWB": TEXT,
    "Carrier": TEXT,
    "Invoice Ref": TEXT,
    "Invoice Date": DATE,
    "Ship Date": DATE,
    "Service Type": TEXT,
    "Charge Type": TEXT,
    "Billed Zone": TEXT,
    "Origin City": TEXT,           # lane
    "Origin Country": TEXT,        # lane
    "Destination City": TEXT,      # lane
    "Destination Country": TEXT,   # lane
    "Pieces": NUMBER,
    "Billed Weight": NUMBER,
    "Weight Unit": TEXT,
    "Billed Weight Unit": TEXT,
    "Actual Weight": NUMBER,
    "Length": NUMBER,
    "Width": NUMBER,
    "Height": NUMBER,
    "Dimension Unit": TEXT,
    "Base Freight": NUMBER,
    "Surcharge Amount": NUMBER,
    "Tax Amount": NUMBER,
    "Total": NUMBER,
    "Currency": TEXT,
}

# Added by the engine, never mapped from a carrier file.
GENERATED_FIELDS = ("Invoice Line ID", "Carrier ID")

# Every mapping must supply these two.
REQUIRED_MAPPED_FIELDS = ("AWB", "Total")

WEIGHT_UNITS = ("kg", "lb")
DIMENSION_UNITS = ("cm", "in")
