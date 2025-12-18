import pandas as pd
import os
from django.conf import settings
import json
from rapidfuzz import fuzz, process
import traceback
import requests
from pprint import pprint

def filingstatus(data):
    result = {}
    result1 = {}
    df_gstr1 = pd.DataFrame()
    df_3b = pd.DataFrame()
    # print("data--->",data)
    try:
        if type(data) == list:
            df = pd.DataFrame(data)
            df_3b = df[df['rtntype'] == 'GSTR3B']
            df_gstr1 = df[df['rtntype'] == 'GSTR1']
            # Convert 'dof' column to datetime format and # Sort by 'dof' in descending order
            df_gstr1.loc[:, 'dof'] = pd.to_datetime(df_gstr1['dof'], format='%d-%m-%Y')
            df_gstr1 = df_gstr1.sort_values(by='dof', ascending=False)
            # Take the top 3 rows
            top_3_rows_df_gstr1 = df_gstr1.head(3)
            if all(top_3_rows_df_gstr1['status'] == 'Filed'):
                result1['status'] = 'Filed'
                result1['month'] = top_3_rows_df_gstr1.iloc[0]['status']
                result1['month1'] = top_3_rows_df_gstr1.iloc[1]['status']
                result1['month2'] = top_3_rows_df_gstr1.iloc[2]['status']
            else:
                result1['status'] = 'Not Filed'
                result1['month'] = top_3_rows_df_gstr1.iloc[0]['status']
                result1['month1'] = top_3_rows_df_gstr1.iloc[1]['status']
                result1['month2'] = top_3_rows_df_gstr1.iloc[2]['status']
            # Convert 'dof' column to datetime format and # Sort by 'dof' in descending order
            df_3b.loc[:, 'dof'] = pd.to_datetime(df_3b['dof'], format='%d-%m-%Y')
            df_3b = df_3b.sort_values(by='dof', ascending=False)
            # Take the top 3 rows
            top_3_rows_df_gstr3b = df_3b.head(3)
            
            if all(top_3_rows_df_gstr1['status'] == 'Filed'):
                result['status'] = 'Filed'
                result['month'] = top_3_rows_df_gstr3b.iloc[0]['status']
                result['month1'] = top_3_rows_df_gstr3b.iloc[1]['status']
                result['month2'] = top_3_rows_df_gstr3b.iloc[2]['status']
            else:
                result['status'] = 'Not Filed'
                result['month'] = top_3_rows_df_gstr3b.iloc[0]['status']
                result['month1'] = top_3_rows_df_gstr3b.iloc[1]['status']
                result['month2'] = top_3_rows_df_gstr3b.iloc[2]['status']
        else:
            result1['status'] = 'Not Filed'
            result1['month'] = data
            result1['month1'] = data
            result1['month2'] = data
            result['status'] = 'Not Filed'
            result['month'] = data
            result['month1'] = data
            result['month2'] = data
    except Exception as e:
        print("An error occurred:", str(e))
        traceback.print_exc()
    return result, result1, df_gstr1, df_3b

def Table_data(table,invoice_data):
    
    basic = invoice_data.get('SubTotal')
    Total = invoice_data.get('InvoiceTotal')
    tax = invoice_data.get('TotalTax')
    df = pd.DataFrame(table)
    print(df)
    check2 = {}
    check3 = {}
    # Columns to check
    required_columns = ['amount', 'qty_unitprice', 'qty_unit+rate_qty_unit', 'qty_unit+2_rate_qty_unit']

    # Find the first matching column
    present_columns = [col for col in required_columns if col in df.columns]
    print('hello')
    try:
        if present_columns:
            first_present_col = present_columns[0]
            left_of_first = df.columns[df.columns.get_loc(first_present_col) - 1] if df.columns.get_loc(first_present_col) > 0 else None

            # Compute sums for the present columns
            sums = {col: df[col].sum() for col in present_columns}

            # Create a new row with sums and blanks for other columns
            new_row = {col: '' for col in df.columns}
            new_row.update(sums)
            if left_of_first:
                new_row[left_of_first] = 'Total->'

            # Append the new row
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        if 'qty_unitprice' in df.columns:
            calculated_sum_check2 = float(df.at[len(df) - 1, 'qty_unitprice'])
        else:
            calculated_sum_check2 = float(df.at[len(df) - 1, 'amount'])
            # Check specific columns for absolute difference with Total
        columns_to_check = ['qty_unit+rate_qty_unit', 'qty_unit+2_rate_qty_unit']
        for col in columns_to_check:
            if col in df.columns:
                # Get the calculated sum for this column (last row)
                calculated_sum = float(df.at[len(df) - 1, col])

                # Compare the absolute difference
                if abs(calculated_sum - float(Total)) > 1:
                    # Drop the column
                    df.drop(columns=[col], inplace=True)
                else:
                    check3['OCR Captured Total Amount-->'] = Total
                    check3[f'Calculated Total Amount-->[ Total of {col} column ]'] = calculated_sum
                    check3['Check3'] = 'Okay'
            else:
                if abs(float(Total)-(calculated_sum_check2+float(tax))) < 1:
                    check3['OCR Captured Total Amount-->'] = Total
                    check3['OCR captured Total Tax'] = tax
                    check3[f'Calculated Total Amount-->[ {tax} + {calculated_sum_check2} ]'] = float(tax)+calculated_sum_check2
                    check3['Check3'] = 'Okay'
                else:
                    check3['OCR Captured Total Amount-->'] = Total
                    check3['OCR captured Total tax'] = tax
                    check3[f'Calculated Total Amount-->[ {tax} {calculated_sum_check2} ]'] = float(tax)+calculated_sum_check2
                    check3['Check3'] = 'Not Okay'
        # calculated_sum_check2 = float(df.at[len(df) - 1, 'qty_unitprice'])
        if 'qty_unitprice' in df.columns and basic:
            if abs(calculated_sum_check2 - float(basic)) > 1:
                check2['OCR Captured Basic Amount-->'] = basic
                check2['Calculated Basic Amount-->[ Total of qty_unitprice column ]'] = calculated_sum_check2
                check2['Check2'] = 'Not Okay'
            else:
                check2['OCR Captured Basic Amount-->'] = basic
                check2['Calculated Basic Amount-->[ Total of qty_unitprice column ]'] = calculated_sum_check2
                check2['Check2'] = 'Okay'
            
        elif 'qty_unitprice' not in df.columns and basic:
            check2['OCR Captured Basic Amount-->'] = basic
            check2['Calculated Basic Amount-->[ Total of qty_unitprice column ]'] = 'Not calculated , Either Unit price or quantity is missing in table'
            check2['Check2'] = 'Not Confirmed, Please check , Either Unit price or quantity is missing in table'
        else:
            check2['OCR Captured Basic Amount-->'] = 'Basic amount not captured by OCR'
            check2['Calculated Basic Amount-->[ Total of qty_unitprice column ]'] = calculated_sum_check2
            check2['Check2'] = 'Not Confirmed, Please check'

        # Convert back to a list of dictionaries
        processed_list_of_dicts = df.to_dict(orient='records')

        print('hello')
        print(processed_list_of_dicts,check2,check3)
        return processed_list_of_dicts , check2 , check3
    except Exception as e:
        print(e)

def InvoiceTable_vs_GrnTable(invoice_data,user_index):
    # print('this---1')
    table = invoice_data.get('Invoice items:')
    invoice_id = invoice_data.get('InvoiceId')
    # print('this---2')
    invoice_date = invoice_data.get('InvoiceDate')
    vendor_gst = invoice_data.get('Vendor Gst No.')
    df = pd.DataFrame.from_dict(table, orient='index')
    # print('this---3')
    if not df.empty:
        # Remove 'column_name' from its original position
        column_name = 'amount'
        # Insert 'column_name' at the last position
        try:
            col = df.pop(column_name)
            df['amount'] = col   
        except KeyError:
            print(f"Column '{column_name}' not found.")
        # print('this---4')
        df1 = df.to_dict(orient='records')
        df_ =  [200,df1]
    else:
        df_ =  [400,'No Table items in invoice']
    # path = 'GRN_DATA/Open_GRN_Data.csv'
    path = os.path.join(settings.BASE_DIR, 'GRN_Data', str(user_index), 'Open_GRN_Data.csv')
    # print('this---5')
    try:
        data = pd.read_csv(path, dtype={'Supplier Ref No': str})
        # print(data['Supplier Ref No'])
        if invoice_id:
            invoice_id = str(invoice_id).lstrip('0')
        # print(invoice_id)
        data = data[data['Supplier Ref No'] == invoice_id]
        # print(data)
        if not data.empty:
            # print('this---5')
            # print(data.columns)
            columns = ['Supplier Ref No','Item No.', 'Item Description', 'Quantity', 'Price', 'Discount %', 'HSN/SAC', 'Total Before Discount']
            data = data[columns]
            # print(data)
            # Convert back to a list of dictionaries
            data1 = data.to_dict(orient='records')
            # print(data1)
            data_ = [200,data1]
        else:
            data_ = [400,'Invoice Id did not match with any record from OPEN GRN , Please Check']
    except:
        data_ = [400,'Please Upload Open GRN reports , found No Reports']
    # print(df_,data_)
    return df_,data_

def Invoicetable_vs_Grntable_compare(invoice_data,user_index):
    result = {}
    table = invoice_data.get('Invoice items:')
    invoice_id = invoice_data.get('InvoiceId')
    invoice_date = invoice_data.get('InvoiceDate')
    vendor_gst = invoice_data.get('Vendor Gst No.')
    supplier_name = invoice_data.get('VendorName') 
    Currency_Type = invoice_data.get('Currency')
    Discount_Amount = invoice_data.get('TotalDiscount')
    Total_Paymt_Due = invoice_data.get('InvoiceTotal')
    df = pd.DataFrame.from_dict(table, orient='index')
    # print('hello--1')
    if not df.empty:
        total_amount = df['amount'].sum()
    if not Total_Paymt_Due:
        Total_Paymt_Due = total_amount
   
    # path = 'GRN_DATA/Open_GRN_Data.csv'
    path = os.path.join(settings.BASE_DIR, 'GRN_Data', str(user_index), 'Open_GRN_Data.csv')
    # print(path,invoice_id)
    try:
        data = pd.read_csv(path, dtype={'Supplier Ref No': str})
        # print(data)
        # print(invoice_id)
        # print(data['Supplier Ref No'])
        if invoice_id:
            invoice_id = str(invoice_id).lstrip('0')
        data = data[data['Supplier Ref No'] == invoice_id]
        
        
        # print(data)
        if not data.empty:
            data_ = data.iloc[0]
            invoice_id_grn = data_['Supplier Ref No']
            supplier_name_grn = data_['Customer/Supplier Name']
            Currency_Type_grn = data_.get('Currency Type Header') or data_.get('Currency Type')
            if Currency_Type_grn == 'INR':
                Total_Paymt_Due_grn = data_['Total Paymt Due']  # Total Paymt Due  Total Paymt Due
            else:
                Total_Paymt_Due_grn = data_['Total Payment Due FC']
            # print(Total_Paymt_Due_grn)
            # print(Total_Paymt_Due)     
            # print('hello--3')  
        # print('hello--2')
    except Exception as e:
        # Print the error message
        print(f"Error: {str(e)}")
        data_ = [400,'Please Upload Open GRN reports , found No Reports']
    invoice_dict = {}
    supplier_name_dict = {}
    Currency_Type_dict = {}
    Total_Paymt_Due_dict = {}
    if invoice_id == invoice_id_grn:
        invoice_dict['Particulars'] = 'Supplier Ref No'
        invoice_dict['As_per_invoice'] = invoice_id
        invoice_dict['As_per_grn'] = invoice_id_grn
        invoice_dict['result'] = 'Matched'
    else:
        invoice_dict['Particulars'] = 'Supplier Ref No'
        invoice_dict['As_per_invoice'] = invoice_id
        invoice_dict['As_per_grn'] = invoice_id_grn
        invoice_dict['result'] = 'Not Matched'

    # supplier_name_ratio = fuzz.token_set_ratio(supplier_name.upper(), supplier_name_grn)
    # Normalize both strings to lowercase
    supplier_name_normalized = supplier_name.lower()
    supplier_name_grn_normalized = supplier_name_grn.lower()

    # Calculate token set ratio after normalization
    supplier_name_ratio = fuzz.token_set_ratio(supplier_name_normalized, supplier_name_grn_normalized)
    # print(supplier_name_ratio)
    if int(supplier_name_ratio) > 85:
        supplier_name_dict['Particulars'] = 'Supplier Name'
        supplier_name_dict['As_per_invoice'] = supplier_name
        supplier_name_dict['As_per_grn'] = supplier_name_grn
        supplier_name_dict['result'] = 'Matched'
    else:
        supplier_name_dict['Particulars'] = 'Supplier Name'
        supplier_name_dict['As_per_invoice'] = supplier_name
        supplier_name_dict['As_per_grn'] = supplier_name_grn
        supplier_name_dict['result'] = 'Not Matched'
    # print(supplier_name_dict)
    Currency_Type_ratio = fuzz.token_set_ratio(Currency_Type, Currency_Type_grn)
    if int(Currency_Type_ratio) > 95:
        Currency_Type_dict['Particulars'] = 'Currency Type'
        Currency_Type_dict['As_per_invoice'] = Currency_Type
        Currency_Type_dict['As_per_grn'] = Currency_Type_grn
        Currency_Type_dict['result'] = 'Matched'
    else:
        Currency_Type_dict['Particulars'] = 'Currency Type'
        Currency_Type_dict['As_per_invoice'] = Currency_Type
        Currency_Type_dict['As_per_grn'] = Currency_Type_grn
        Currency_Type_dict['result'] = 'Not Matched'
    # print(Currency_Type_dict)
    
    # print(type(Total_Paymt_Due),Total_Paymt_Due_grn)
    # print('hello---6')
    if abs(float(Total_Paymt_Due) - float(Total_Paymt_Due_grn)) < 1:
        Total_Paymt_Due_dict['Particulars'] = 'Total Paymt Due'
        Total_Paymt_Due_dict['As_per_invoice'] = Total_Paymt_Due
        Total_Paymt_Due_dict['As_per_grn'] = float(Total_Paymt_Due_grn)
        Total_Paymt_Due_dict['result'] = 'Matched'
    else:
        Total_Paymt_Due_dict['Particulars'] = 'Total Paymt Due'
        Total_Paymt_Due_dict['As_per_invoice'] = Total_Paymt_Due
        Total_Paymt_Due_dict['As_per_grn'] = Total_Paymt_Due_grn
        Total_Paymt_Due_dict['result'] = 'Not Matched'
    # print(Total_Paymt_Due_dict)
    result['invoice_id_match'] = invoice_dict
    result['supplier_name_match'] = supplier_name_dict
    result['Currency_Type_match'] = Currency_Type_dict
    result['Total_Paymt_Due_match'] = Total_Paymt_Due_dict
    # print(result)
    return result

def all_okay(api_response):
    result_ = {}
    status = 'All Okay'
    message = []
    
    try:
        if api_response:
            result = api_response.get("result", {})
            acount_check = result.get('CHECKS', {}).get('Account_check', {})
            tax_check = result.get('CHECKS', {}).get('tax_check', {})
            table_check = result.get('CHECKS', {}).get('table_data', {}).get('Table_Check_data', [])
            invoice_data = result.get('Invoice_data', {})

            # -------- Account Check Validations -------- #
            fields_account = {
                'Complete_Invoice': 'Not a Complete_Invoice',
                'Customer_Adress': 'Customer_Adress Not Matched',
                'Customer_Name': 'Customer_Name Not Matched',
                'Invoice_Blocked_Credit': 'Invoice_Blocked_Credit Type',
                'Invoice_Date': 'Invoice_Date is not captured or not present',
                'Invoice_Number': 'Invoice_Number Not Captured or not present',
                'Invoice_RCM-Services': 'Invoice_RCM-Services Type',
                'Pre_year': 'Invoice is from Previous year',
                'gstnumber_gstcharged': 'gstnumber_gstcharged Not Okay',
                'valid_invoice': 'Invoice is Invalid'
            }
            expected_account = {
                'Complete_Invoice': 'YES',
                'Customer_Adress': 'Matching',
                'Customer_Name': 'Matching',
                'Invoice_Blocked_Credit': 'Okay',
                'Invoice_Date': 'Okay',
                'Invoice_Number': 'Okay',
                'Invoice_RCM-Services': 'NO',
                'Pre_year': 'NO',
                'gstnumber_gstcharged': 'Okay',
                'valid_invoice': 'YES'
            }

            for key, fail_msg in fields_account.items():
                try:
                    if acount_check[key]['status'] != expected_account[key]:
                        status = 'Not All Okay'
                        message.append(fail_msg)
                except Exception as e:
                    status = 'Not All Okay'
                    message.append(f"{key} check failed due to missing or malformed data")

            # -------- Tax Check Validations -------- #
            fields_tax = {
                'Company_Gst_Valid': 'Company_Gst_Valid',
                'Company_Gst_mentioned': 'Company_Gst_mentioned',
                'Vendor_206AB': 'Vendor_206AB',
                'Vendor_Filing_status': 'Vendor_Filing_status',
                'Vendor_Gst_Active': 'Vendor_Gst not Active',
                'Vendor_Gst_Valid': 'Vendor_Gst inValid',
                'Vendor_Gst_mentioned': 'Vendor_Gst not mentioned',
                'Vendor_Pan-Adhar_Linked': 'Vendor_Pan-Adhar not Linked',
                'Vendor_Pan_Active': 'Vendor_Pan not Active',
                'tax_type_on_invoice': 'tax_type_on_invoice'
            }
            expected_tax = {
                'Company_Gst_Valid': 'YES',
                'Company_Gst_mentioned': 'YES',
                'Vendor_206AB': 'Okay',
                'Vendor_Filing_status': 'filled',
                'Vendor_Gst_Active': 'YES',
                'Vendor_Gst_Valid': 'YES',
                'Vendor_Gst_mentioned': 'YES',
                'Vendor_Pan-Adhar_Linked': 'Okay',
                'Vendor_Pan_Active': 'Okay',
                'tax_type_on_invoice': 'Okay'
            }

            for key, fail_msg in fields_tax.items():
                try:
                    if tax_check[key]['status'] != expected_tax[key]:
                        status = 'Not All Okay'
                        message.append(fail_msg)
                except Exception as e:
                    status = 'Not All Okay'
                    message.append(f"{key} check failed due to missing or malformed data")

            # -------- Table Check 1 -------- #
            try:
                parsed_data = json.loads(table_check)
                df = pd.DataFrame(parsed_data)
                
            except Exception as e:
                print("Error in Table_check1:", e)
                traceback.print_exc()
            try:
                if 'check1' in df.columns:
                    if (df['check1'] == 'correct').all():
                        Table_check1 = 'Okay'
                    else:
                        status = 'Not All Okay'
                        message.append('Table_check1 not okay')
                else:
                    status = 'Not All Okay'
                    message.append('Table_check1 not found in table')
            except Exception as e:
                status = 'Not All Okay'
                message.append('Table_check1 skipped due to error')
                print("An error occurred in Table_check1:", str(e))
                traceback.print_exc()

            # -------- Table Check 2 -------- #
            try:
                basic_amount = invoice_data.get('SubTotal')
                if basic_amount:
                    if 'qty_unitprice' in df.columns:
                        try:
                            calculated_basic = df['qty_unitprice'].astype(float).sum()
                            if abs(calculated_basic - float(basic_amount)) < 1:
                                table_check2 = 'Okay'
                            else:
                                status = 'Not All Okay'
                                message.append('Table_Check2 not okay')
                        except Exception as e:
                            status = 'Not All Okay'
                            message.append('Table_Check2 calculation failed for qty_unitprice')
                    elif 'amount' in df.columns:
                        try:
                            calculated_basic = df['amount'].astype(float).sum()
                            if abs(calculated_basic - float(basic_amount)) < 1:
                                table_check2 = 'Okay'
                            else:
                                status = 'Not All Okay'
                                message.append('Table_Check2 not okay')
                        except Exception as e:
                            status = 'Not All Okay'
                            message.append('Table_Check2 calculation failed for amount')
                    else:
                        status = 'Not All Okay'
                        message.append('Table_Check2 not confirmed: amount or qty_unitprice missing')
                else:
                    status = 'Not All Okay'
                    message.append('Table_Check2 skipped: SubTotal missing in invoice')
            except Exception as e:
                status = 'Not All Okay'
                message.append('Table_Check2 not performed due to complex table or data error')
                print("Error in Table_check2:", e)
                traceback.print_exc()

            # Final result
            result_['status'] = status
            result_['message'] = message

            # Add to api_response
            if "result" in api_response:
                api_response["result"]["Okay_NotOkay"] = result_
            else:
                api_response["result"] = {"Okay_NotOkay": result_}

            return result_, api_response

        else:
            result_['status'] = "No Response"
            result_['message'] = 'API response is empty or invalid'
            return result_, api_response

    except Exception as e:
        print("An error occurred at top level:", e)
        traceback.print_exc()
        result_['status'] = 'Not All Okay'
        message.append("Top-level error occurred during processing")
        result_['message'] = message
        return result_, api_response


def get_exchange_rate(base_currency, target_currency, date='latest'):
    base_currency = base_currency.lower()
    target_currency = target_currency.lower()

    primary_url = f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/{base_currency}.json"
    fallback_url = f"https://{date}.currency-api.pages.dev/v1/currencies/{base_currency}.json"

    try:
        response = requests.get(primary_url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Primary failed: {e}\nTrying fallback...")
        try:
            response = requests.get(fallback_url, timeout=5)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Fallback failed: {e}")
            return None

    try:
        rate = data[base_currency][target_currency]
        return rate
    except KeyError:
        print(f"Conversion from {base_currency.upper()} to {target_currency.upper()} not available.")
        return None   
    
if __name__ == "__main__":
    
    data1 = [{'arn': 'AB290325747755N',
            'dof': '22-04-2025',
            'mof': 'ONLINE',
            'ret_prd': '032025',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB291124240201R',
            'dof': '20-12-2024',
            'mof': 'ONLINE',
            'ret_prd': '112024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB291024261110R',
            'dof': '20-11-2024',
            'mof': 'ONLINE',
            'ret_prd': '102024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB290824282196N',
            'dof': '20-09-2024',
            'mof': 'ONLINE',
            'ret_prd': '082024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB2907243014951',
            'dof': '20-08-2024',
            'mof': 'ONLINE',
            'ret_prd': '072024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB2905243610555',
            'dof': '20-06-2024',
            'mof': 'ONLINE',
            'ret_prd': '052024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB290424271506Z',
            'dof': '20-05-2024',
            'mof': 'ONLINE',
            'ret_prd': '042024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB290225378513Y',
            'dof': '20-03-2025',
            'mof': 'ONLINE',
            'ret_prd': '022025',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB2912242402396',
            'dof': '20-01-2025',
            'mof': 'ONLINE',
            'ret_prd': '122024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB290924428585K',
            'dof': '19-10-2024',
            'mof': 'ONLINE',
            'ret_prd': '092024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB2906242495013',
            'dof': '19-07-2024',
            'mof': 'ONLINE',
            'ret_prd': '062024',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AB2901251475048',
            'dof': '19-02-2025',
            'mof': 'ONLINE',
            'ret_prd': '012025',
            'rtntype': 'GSTR3B',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA291124540531H',
            'dof': '11-12-2024',
            'mof': 'ONLINE',
            'ret_prd': '112024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA291024528521G',
            'dof': '11-11-2024',
            'mof': 'ONLINE',
            'ret_prd': '102024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290924551002A',
            'dof': '11-10-2024',
            'mof': 'ONLINE',
            'ret_prd': '092024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290824525030F',
            'dof': '11-09-2024',
            'mof': 'ONLINE',
            'ret_prd': '082024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA2906246095035',
            'dof': '11-07-2024',
            'mof': 'ONLINE',
            'ret_prd': '062024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290524483736M',
            'dof': '11-06-2024',
            'mof': 'ONLINE',
            'ret_prd': '052024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA2904245250981',
            'dof': '11-05-2024',
            'mof': 'ONLINE',
            'ret_prd': '042024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290325627214A',
            'dof': '11-04-2025',
            'mof': 'ONLINE',
            'ret_prd': '032025',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290225551907U',
            'dof': '11-03-2025',
            'mof': 'ONLINE',
            'ret_prd': '022025',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290125570992U',
            'dof': '11-02-2025',
            'mof': 'ONLINE',
            'ret_prd': '012025',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA291224507435A',
            'dof': '11-01-2025',
            'mof': 'ONLINE',
            'ret_prd': '122024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'},
            {'arn': 'AA290724447749F',
            'dof': '10-08-2024',
            'mof': 'ONLINE',
            'ret_prd': '072024',
            'rtntype': 'GSTR1',
            'status': 'Filed',
            'valid': 'Y'}]

    data2 = [{'item_description': 'HSS Drill Bit 5.4mm', 'item_quantity': 5.0, 'unit_price': 102.2, 'product_code': '8207', 'tax_rate': 18, 'amount': 511.0, 'qty_unitprice': 511.0, 'qty_unit+rate_qty_unit': 602.98, 'qty_unit+2_rate_qty_unit': 694.96, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 5.5mm', 'item_quantity': 5.0, 'unit_price': 102.85, 'product_code': '8207', 'tax_rate': 18, 'amount': 514.25, 'qty_unitprice': 514.25, 'qty_unit+rate_qty_unit': 606.815, 'qty_unit+2_rate_qty_unit': 699.38, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 3.6mm', 'item_quantity': 20.0, 'unit_price': 47.92, 'product_code': '8207', 'tax_rate': 18, 'amount': 958.4, 'qty_unitprice': 958.4, 'qty_unit+rate_qty_unit': 1130.912, 'qty_unit+2_rate_qty_unit': 1303.424, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 3.7mm', 'item_quantity': 20.0, 'unit_price': 47.92, 'product_code': '8207', 'tax_rate': 18, 'amount': 958.4, 'qty_unitprice': 958.4, 'qty_unit+rate_qty_unit': 1130.912, 'qty_unit+2_rate_qty_unit': 1303.424, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 4.2mm', 'item_quantity': 10.0, 'unit_price': 69.62, 'product_code': '8207', 'tax_rate': 18, 'amount': 696.2, 'qty_unitprice': 696.2, 'qty_unit+rate_qty_unit': 821.516, 'qty_unit+2_rate_qty_unit': 946.832, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 4.3mm -', 'item_quantity': 10.0, 'unit_price': 69.62, 'product_code': '8207', 'tax_rate': 18, 'amount': 696.2, 'qty_unitprice': 696.2, 'qty_unit+rate_qty_unit': 821.516, 'qty_unit+2_rate_qty_unit': 946.832, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 2.4mm', 'item_quantity': 10.0, 'unit_price': 29.93, 'product_code': '8207', 'tax_rate': 18, 'amount': 299.3, 'qty_unitprice': 299.3, 'qty_unit+rate_qty_unit': 353.174, 'qty_unit+2_rate_qty_unit': 407.048, 'check1': 'correct'},
            {'item_description': 'HSS Drill Bit 2.5mm', 'item_quantity': 10.0, 'unit_price': 29.93, 'product_code': '8207', 'tax_rate': 18, 'amount': 299.3, 'qty_unitprice': 299.3, 'qty_unit+rate_qty_unit': 353.174, 'qty_unit+2_rate_qty_unit': 407.048, 'check1': 'correct'},
            {'item_description': 'Pop Rivit Gun', 'item_quantity': 1.0, 'unit_price': 950.0, 'product_code': '8405', 'tax_rate': 18, 'amount': 950.0, 'qty_unitprice': 950.0, 'qty_unit+rate_qty_unit': 1121.0, 'qty_unit+2_rate_qty_unit': 1292.0, 'check1': 'correct'}]

    invoice_data__ = {'Bank_Details': {'Account_holder_name': 'AMITH INC.,', 'Bank_Account_No': None, 'Bank_Branch': 'PEENYA INDUS  ESTATE BANGALORE', 'Bank_Name': 'State Bank of India', 'Email': None, 'IFSC_Code': 'SBIN0003024', 'VendorAddress': '#21A, 3rd a cross potti gardens s.m. road bangalore 560, None, None, None, None'},
                    'BillingAddress': 'None, Mahadevapura, Bangalore, None, 560 048, None', 
                    'BillingAddressRecipient': 'Glodesi Technologies Pvt Ltd.,', 
                    'Currency': 'INR', 
                    'CustomerName': 'Glodesi Technologies Pvt Ltd.,', 
                    'Cutomer Gst No.': '29AAGCG0335D2ZX', 
                    'Invoice items:': {'item#1': {'amount': '2975.0', 'item_description': 'PRECOIL M2×0.4×1.5D (3mm)', 'item_quantity': 700.0, 'product_code': 'SDMC02.0150\n73181190', 'unit': 'nos', 'unit_price': '4.25'}, 
                                        'item#2': {'amount': '690.0', 'item_description': 'PRECOIL M3x0.5x1.5D (4.5mm)', 'item_quantity': 300.0, 'product_code': 'SDMC03.0150\n73181190', 'unit': 'nos', 'unit_price': '2.3'}, 
                                        'item#3': {'amount': '690.0', 'item_description': 'STI Tap M2x0.4 ET', 'item_quantity': 1.0, 'product_code': '82074090', 'unit': 'nos', 'unit_price': '690.0'}, 
                                        'item#4': {'amount': '500.0', 'item_description': 'PRECOIL Inserting Tool M2x0.4', 'item_quantity': 1.0, 'product_code': '82041110', 'unit': 'nos', 'unit_price': '500.0'}}, 
                    'InvoiceDate': '2024-11-14', 
                    'InvoiceId': '3385/24-25', 
                    'InvoiceTotal': '5729.00', 
                    'PurchaseOrder': '241100417-\n24351025', 
                    'SubTotal': '4855.00', 
                    'Tax Items': {'CGST': {'amount': '436.95'}, 'SGST': {'amount': '436.95'}}, 
                    'TotalTax': '873.90', 
                    'Vendor Gst No.': '29BCUPS8159M1Z7', 
                    'VendorAddress': '#21A, 3rd a cross potti gardens s.m. road bangalore 560, None, None, None, None', 
                    'VendorAddressRecipient': 'AMITH INC.,', 
                    'VendorName': 'AMITH INC.,'}

    pprint(filingstatus(data1))
    # total = 6942.00
    # bas = 5883.05
    # InvoiceTable_vs_GrnTable(invoice_data__)