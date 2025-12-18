SYSTEM_VARIABLES = [
    {"name": "CompanyCode", "source": "MIGO"},
    {"name": "VendorGst", "source": "OCR"},
    {"name": "DocumentNumber", "source": "MIGO"},
    {"name": "DocType", "source": "OCR"},
    {"name": "InvoiceDate", "source": "MIGO"},
    {"name": "PostingDate", "source": "Config"},
    {"name": "AP_Inv_doc_num", "source": "MIGO"},
    {"name": "Currency", "source": "MIGO"},
    {"name": "ExchangeRate", "source": "MIGO"},
    {"name": "VendorCode", "source": "MIGO"},
    {"name": "PaymentTerms", "source": "MIGO"},
    {"name": "BaselineDate", "source": "MIGO"},
    {"name": "PO_Number", "source": "MIGO"},
    {"name": "PO_Item", "source": "MIGO"},
    {"name": "GR_Number", "source": "MIGO"},
    {"name": "MaterialNo", "source": "MIGO"},
    {"name": "Qty_Invoiced", "source": "MIGO"},
    {"name": "UoM", "source": "MIGO"},
    {"name": "NetPrice", "source": "MIGO"},
    {"name": "InvoiceAmount", "source": "MIGO"},
    {"name": "TaxCode", "source": "MIGO"},
    {"name": "TaxAmount", "source": "MIGO"},
    {"name": "WithholdingTaxCode", "source": "MIGO"},
    {"name": "UnplannedDeliveryCost", "source": "MIGO"},
    {"name": "GLAccount", "source": "MIGO"},
    {"name": "CostCenter", "source": "MIGO"},
    {"name": "WBS_Element", "source": "PO"},
    {"name": "AssetNo", "source": "MIGO"},
    {"name": "PaymentBlock", "source": "Config"},
    {"name": "Narration", "source": "Config"},
    {"name": "MigoDocDate", "source": "MIGO"},
    {"name": "SuppInv_no", "source": "MIGO"},
    {"name": "item_descritption", "source": "MIGO"},
    {"name": "item_rate", "source": "MIGO"}
    
]

DOCTYPE = {
    'invoice':'I',
    'credit':'C'
}
radio = {"r1": {
        "2/3way": {
            "color": "g",
            "data": [
                {
                    "color": "g",
                    "grn_description": "Shroud Family Mold Tool (8 and 18 pole)",
                    "grn_qty": "1",
                    "grn_rate": "250000.0",
                    "item_description": "300177_Shroud Family Mold Tool (8 and 18 pole) .",
                    "item_quantity": 1.0,
                    "matching%": 73.56,
                    "status": "matched",
                    "unit_price": "250000.0"
                },
                {
                    "color": "g",
                    "grn_description": "Housing Family Mold Tool (8 and 18 pole)",
                    "grn_qty": "1",
                    "grn_rate": "250000.0",
                    "item_description": "300178_Housing Family Mold Tool (8 and 18 pole) .",
                    "item_quantity": 1.0,
                    "matching%": 71.91,
                    "status": "matched",
                    "unit_price": "250000.0"
                },
                {
                    "color": "g",
                    "grn_description": "Big Terminal Semi progressive tool (8 and 18 pole)",
                    "grn_qty": "1",
                    "grn_rate": "130000.0",
                    "item_description": "300179_Big Terminal Semi progressive tool (8 and 18\npole)",
                    "item_quantity": 1.0,
                    "matching%": 85.98,
                    "status": "matched",
                    "unit_price": "130000.0"
                },
                {
                    "color": "g",
                    "grn_description": "Small Terminal Semi progressive tool (8 and 18 pole)",
                    "grn_qty": "1",
                    "grn_rate": "130000.0",
                    "item_description": "300180_Small Terminal Semi progressive tool (8 and 18\npole) .",
                    "item_quantity": 1.0,
                    "matching%": 81.42,
                    "status": "matched",
                    "unit_price": "130000.0"
                },
                {
                    "color": "g",
                    "grn_description": "Bending tool (8 and 18 pole)",
                    "grn_qty": "1",
                    "grn_rate": "40000.0",
                    "item_description": "300181_Bending tool (8 and 18 pole) .",
                    "item_quantity": 1.0,
                    "matching%": 73.85,
                    "status": "matched",
                    "unit_price": "40000.0"
                }
            ],
            "message": "2/3 way match result"
        },
        "color": "r",
        "invoice_calulation1": {
            "color": "g",
            "ocr_captured_amount": 800000.0,
            "table_sum_of_item_level": 800000.0
        },
        "invoice_calulation2": {
            "color": "g",
            "ocr_captured_total_amount": 944000.0,
            "table_calculated_amount+ocr_captured_tax": 944000.0
        },
        "otherchecks": {
            "exchange_rate": {
                "Difference": "Migo Exchange Rate Missing or 0or Column is not mapped",
                "Invoice/OCR": 1,
                "Migo": "Excahnge Rate Column is not mapped with Migo Data Column",
                "color": "r"
            },
            "inv_date": {
                "Difference": "Yes",
                "Invoice/OCR": "2025-03-31",
                "Migo": "2025-04-07 00:00:00",
                "color": "r"
            },
            "payment_check": {}
        }
    }}
# {'CompanyCode': '9300', 'DocumentNumber': '5013275403', 'InvoiceDate': '2024-10-25 00:00:00', 
#  'Currency': 'INR', 'VendorCode': '45686', 'PaymentTerms': 'V006', 'BaselineDate': 'None', 
#  'PO_Number': '9300005808', 'PO_Item': '1', 'GR_Number': '5013275403', 'MaterialNo': 'S002-1424-00030', 
#  'Qty_Invoiced': '20', 'UoM': 'EA', 'NetPrice': 'None', 'InvoiceAmount': '150000', 'TaxCode': 'V0', 
#  'TaxAmount': '0', 'GLAccount': '121301', 'CostCenter': 'ADS', 'AssetNo': '123456', 'MigoDocDate': 'None', 
#  'SuppInv_no': '498.65', 'vendor_code': '45686', 'document_number': '5013275403', 'inv_no': '49865', 
#  'status': 'pending'}

# {'monthly_close': 'N', 'date_of_entry': 'system', 'auto_on_date': None, 'auto_or_manual': 'automatic', 
#  'scenario_same_month': 'migo', 
#  'scenario_books_closed': 'first_day', 'scenario_books_not_closed': 'migo'}
# {'baseline_active': 'N', 'baseline_choice': 'posting'}
## blocking decision
#{"pan_inactive": {"acc": "N", "pay": "Y", "months": ""}, 
# "aadhar_pan": {"acc": "N", "pay": "N", "months": ""}, 
# "gst_inactive": {"acc": "N", "pay": "Y", "months": ""}, 
# "gstr1": {"acc": "N", "pay": "N", "months": ""}, 
# "gstr3b": {"acc": "N", "pay": "N", "months": ""}, 
# "gst_2b": {"acc": "N", "pay": "N", "months": ""}, 
# "new_vendor": {"acc": "N", "pay": "N", "months": ""}, 
# "regular_vendor": {"acc": "N", "pay": "N", "months": ""}, 
# "prev_gst": {"acc": "N", "pay": "N", "months": ""}}

# for r in radio["r1"]:
#     print(r)
    