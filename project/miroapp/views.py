
from django.shortcuts import render, redirect
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from .forms import CompanyDetailsForm
from .other_functions import send_email
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
# from .models import User, CompanyDetails, Header, OpenGRNData, InvoiceDetail, Configurations, SystemVariableMapping
from .models import *
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db import IntegrityError, connection, transaction
from decimal import Decimal
from django.db.utils import ProgrammingError
import json
import pandas as pd
import threading, requests
import logging
from datetime import datetime, date
import os
from django.db.models import Sum
import time
from django.conf import settings
from django.core.files.storage import default_storage
import traceback
import re
from collections import OrderedDict, defaultdict
import random
from django.core.cache import cache
from .diffrent_functions import filingstatus,Table_data,InvoiceTable_vs_GrnTable,all_okay,Invoicetable_vs_Grntable_compare,get_exchange_rate
from .constants import SYSTEM_VARIABLES, DOCTYPE
from .data_gathering import api_response_test
from .table_matching import map_rows

 

logger = logging.getLogger(__name__)

class CustomTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # You can adjust this based on your model fields
        value = str(user.email) + str(timestamp)  # Use User.email instead
        return salted_hmac(self.key_salt, value).hexdigest()

    def get_email_field_name(self):
        return 'email'  # Explicitly define the email field name here

custom_token_generator = CustomTokenGenerator()


def signup(request):
    if request.method == 'POST':
        # Step 1: If OTP verification step
        if 'otp' in request.POST:
            email = request.POST.get('email')
            entered_otp = request.POST.get('otp')
            saved_otp = cache.get(f"otp_{email}")

            if saved_otp and str(saved_otp) == entered_otp:
                cache.delete(f"otp_{email}")
                # OTP verified → now create the company, user, and partitions
                form_data = cache.get(f"signup_data_{email}")
                if not form_data:
                    return JsonResponse({'success': False, 'message': 'Session expired. Please sign up again.'})

                form = CompanyDetailsForm(form_data)
                if form.is_valid():
                    try:
                        with transaction.atomic():
                            company = form.save(commit=False)
                            company.last_login = timezone.now()
                            company.save()

                            # Create the User entry
                            user = User.objects.create(
                                username=company.contact_person_email,
                                email=company.contact_person_email,
                                company_code=company,
                                role='SuperUser',
                            )
                            user.set_unusable_password()
                            user.save()

                            

                            # Send reset password link
                            token = custom_token_generator.make_token(user)
                            uid = urlsafe_base64_encode(user.email.encode('utf-8'))
                            current_site = get_current_site(request)
                            domain = current_site.domain
                            link = f"http://{domain}/reset-password/{uid}/{token}/"

                            subject = "Set your password"
                            message = f'''
                                <html>
                                    <body>
                                        <p>Dear {company.contact_person_name},</p>
                                        <p>Click the link below to reset your password:</p>
                                        <p><a href="{link}" target="_blank">Reset Password</a></p>
                                    </body>
                                </html>
                            '''
                            send_email('nasim.ahmed@blueconsulting.co.in', 'India@1234',
                                       company.contact_person_email, subject, body=message)

                            return redirect('password_reset_confirmation')

                    except Exception as e:
                        print(f"Signup process failed: {str(e)}")
                        return JsonResponse({'success': False, 'message': 'Signup failed. Please try again.'})
                else:
                    return JsonResponse({'success': False, 'message': 'Invalid form data during OTP verification.'})

            else:
                return JsonResponse({'success': False, 'message': 'Invalid or expired OTP. Please try again.'})

        # Step 2: First form submission → send OTP
        else:
            form = CompanyDetailsForm(request.POST)
            if form.is_valid():
                email = form.cleaned_data['contact_person_email']
                otp = random.randint(100000, 999999)

                # Store OTP and form data in cache (valid for 5 minutes)
                cache.set(f"otp_{email}", otp, timeout=300)
                cache.set(f"signup_data_{email}", request.POST, timeout=300)

                # Send OTP email
                send_email('nasim.ahmed@blueconsulting.co.in', 'India@1234', email,
                           "Verify Your Email", f"Your OTP is {otp}. It is valid for 5 minutes.")

                return render(request, 'verify_otp.html', {'email': email})  # Render OTP input page

    # Initial GET request → show signup form
    form = CompanyDetailsForm()
    return render(request, 'signup.html', {'form': form})



def reset_password(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        # print(uid)
        user = User.objects.get(email=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and custom_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            # print('hello')
            # print(new_password,new_password)
            if new_password == confirm_password:
                user.password = make_password(new_password)
                user.save()
                return redirect('login')  # Redirect to login after successful password reset
            else:
                return render(request, 'reset_password.html', {'error': 'Passwords do not match.'})
        return render(request, 'reset_password.html', {'uid': uid, 'token': token})
    else:
        return render(request, 'password_reset_failed.html', {'error': 'The token is expired or invalid. A new link has been sent to your email.'})
    
# This view is for the confirmation page after the password has been successfully reset.
def password_reset_confirmation(request):
    return render(request, 'password_reset_confirmation.html')

def loginview(request):
    if request.method == 'POST':
        username = request.POST['email']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session["company_code"] = user.company_code_id
            # Check if 'next' is in the request and redirect there
            next_url = request.GET.get('next')  # Capture the 'next' parameter
            if next_url:
                return redirect(next_url)
            if user.role == 'SuperUser':
                return redirect('superuser_dashboard')
            elif user.role == 'Processor':
                return redirect('invoices')
            elif user.role == 'Checker' or user.role == 'Module Admin':
                return redirect('checker_dashboard')
            elif user.role == 'Uploader':
                return redirect('uploader_dashboard')
            else:
                return redirect('user_dashboard')
        else:
            # Show user-friendly message
            error_message = "Entered credentials are incorrect. Please enter correct credentials."
            return render(request, 'login.html', {'error': error_message})
    return render(request, 'login.html')


def user_logout(request):
    logout(request)
    request.session.flush()  # Clears all session data
    return redirect("login")

@login_required
def checker_dashboard(request):
    return render(request, 'checker_home.html', {'message': 'This is Checker home Page'})

@login_required
def uploader_dashboard(request):
    company = request.user.company_code
    pendingInvoices = PendingInvoices.objects.filter(company_id=company).order_by('-created_at')

    return render(request, 'uploader_home.html', {
        'data': pendingInvoices
    })


@login_required
def admin_dashboard(request):
    return render(request, 'config_home.html', {'message': 'This is superuser home Page'})


@login_required
@csrf_exempt
def save_configuration(request):
    if request.method == "POST":
        company = request.user.company_code  # assuming user has company_code FK

        # payload comes as a string field in FormData
        payload_str = request.POST.get("payload")
        if not payload_str:
            return JsonResponse({"error": "No payload received"}, status=400)

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON payload"}, status=400)
        # --- NORMALIZE ALL FIELDS ---
        def ensure_dict(value):
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except:
                    return value
            return value
        # def ensure_json_dict(value):
        #     # Already a dict → OK
        #     if isinstance(value, dict):
        #         return value

        #     # String that might contain JSON → try decode
        #     if isinstance(value, str):
        #         try:
        #             return json.loads(value)
        #         except:
        #             return value  # leave normal string unchanged

        #     return value

        for key in list(payload.keys()):
            payload[key] = ensure_dict(payload[key])
        print(payload)
        
        matching = payload.get("matching", {})
        # print(matching)
        matching_type = matching.get("matching_type", "").lower()  # 2way or 3way

        # ✅  Mapping Validation Based on Matching Type
        # success, message = validate_mapping(company,matching_type)
        
        # if not success:
        #     return JsonResponse({
        #         "status": "error",
        #         "message": (
        #             f"Configuration cannot be saved. Mapping incomplete: {message}"
        #         )
        #     }, status=400)

        # Debug print 
        print("Received payload:", payload)

        # ✅ Save to Configurations model
        config, created = Configurations.objects.update_or_create(
            company=company,
            defaults={
                "monthly_close": payload.get("monthly_close", {}),
                "baseline": payload.get("baseline", {}),
                "blocking": payload.get("blocking", {}),
                "matching": payload.get("matching", {}),
                "currency": payload.get("currency", {}),
                "narration": payload.get("narration", {}),
                "duplicate_check": payload.get("duplicate_check", {}),
                "unplanned_cost": payload.get("unplanned_cost", {}),
                "threshold": payload.get("threshold", {}),
                "service_entry_migo": payload.get("service_entry_migo", {}),
                "matching_logic_ratio": payload.get("matching_logic", {}),
                "data_upload_rights": payload.get("data_upload_rights", {}),
            }
        )

        # message = "Configuration created" if created else "Configuration updated"
        message = "Configuration created"
        return JsonResponse({"status": "success", "message": message})

    return JsonResponse({"error": "Invalid request method"}, status=405)
def get_configuration(request):
    company = request.user.company_code  # same company reference you are using

    try:
        config = Configurations.objects.get(company=company)
        return JsonResponse({
            "status": "success",
            "data": {
                "monthly_close": config.monthly_close,
                "baseline": config.baseline,
                "blocking": config.blocking,
                "matching": config.matching,
                "currency": config.currency,
                "narration": config.narration,
                "duplicate_check": config.duplicate_check,
                "unplanned_cost": config.unplanned_cost,
                "threshold": config.threshold,
                "service_entry_migo": config.service_entry_migo,
                "matching_logic_ratio": config.matching_logic_ratio,
                "data_upload_rights": config.data_upload_rights,
            }
        })
    except Configurations.DoesNotExist:
        return JsonResponse({"status": "empty"})
    
def validate_mapping(company_id, matching_type):
    required_vars = ['Qty_Invoiced', 'NetPrice', 'item_description']
    # print(matching)
    # Get matching type from payload (case-insensitive)
    # matching_type = matching.get("matching_type", "").lower()

    # Fetch mappings for required variables
    mappings = SystemVariableMapping.objects.filter(
        company_id=company_id,
        system_var__in=required_vars
    )

    # CASE 0: Check if all required system_var exist in DB
    if mappings.count() != len(required_vars):
        missing_vars = list(set(required_vars) - set(mappings.values_list("system_var", flat=True)))
        return False, f"Mapping not done for fields: {', '.join(missing_vars)}"

    lookup = {m.system_var: m for m in mappings}

    # ----- CASE 1 : 2-WAY MATCHING → Only MIRO mapping is needed -----
    if matching_type == "2way":
        for var in required_vars:
            if not lookup[var].miro_header or lookup[var].miro_header.strip() == "":
                return False, f"MIRO header mapping missing for: {var}"
        return True, "Mapping OK for 2-way matching."

    # ----- CASE 2 : 3-WAY MATCHING → Both PO & MIRO headers required -----
    if matching_type == "3way":
        for var in required_vars:
            if not lookup[var].miro_header or lookup[var].miro_header.strip() == "":
                return False, f"MIRO header mapping missing for: {var}"
            if not lookup[var].po_header or lookup[var].po_header.strip() == "":
                return False, f"PO header mapping missing for: {var}"
        return True, "Mapping OK for 3-way matching."

    # ----- CASE 0 : No matching type selected → Only check presence of rows -----
    return True, "Required mapping variables exist."

@login_required
def home(request):
    return render(request, 'home.html')

@login_required
def upload_header(request):
    if request.method == "GET":
        return render(request, "upload_header.html")

    if request.method == "POST":
        po_file = request.FILES.get("po_header")
        miro_file = request.FILES.get("miro_header")
        se_file = request.FILES.get("se_header")
        vendor_master_file = request.FILES.get("vmaster_header")
        wholdtax_master_file = request.FILES.get("wholdtax_master_header")
        gsttax_master_file= request.FILES.get("gsttax_master_header")
        hsn_master_file= request.FILES.get("hsn_master_header")
        sac_master_file= request.FILES.get("sac_master_header")

        company = request.user.company_code  # This is a CompanyDetails instance

        header_obj, created = Header.objects.get_or_create(company=company)

        # Read PO headers if file provided
        if po_file:
            df_po = pd.read_excel(po_file, nrows=0)
            po_header = [col.strip() for col in df_po.columns if isinstance(col, str)]
            header_obj.po_header = po_header  # update only PO headers
        

        # Read MIRO headers if file provided
        if miro_file:
            df_miro = pd.read_excel(miro_file, nrows=0)
            migo_headers = [col.strip() for col in df_miro.columns if isinstance(col, str)]
            header_obj.miro_header = migo_headers  # update only MIRO headers
      
        
        # Read MIRO headers if file provided
        if se_file:
            df_se = pd.read_excel(se_file, nrows=0)
            se_headers = [col.strip() for col in df_se.columns if isinstance(col, str)]
            header_obj.se_headers = se_headers  # update only MIRO headers
        

        if vendor_master_file:
            df_vendor_master = pd.read_excel(vendor_master_file, nrows=0)
            vendor_master_header = [col.strip() for col in df_vendor_master.columns if isinstance(col, str)]
            # print(vendor_master_header)
            header_obj.vendor_master_header = vendor_master_header  # update only MIRO headers

        if wholdtax_master_file:
            df_vendor_master = pd.read_excel(wholdtax_master_file, nrows=0)
            wholdtax_master_headers = [col.strip() for col in df_vendor_master.columns if isinstance(col, str)]
            header_obj.wholdtax_master_headers = wholdtax_master_headers  # update only MIRO headers

        if gsttax_master_file:
            df_vendor_master = pd.read_excel(gsttax_master_file, nrows=0)
            gsttax_master_headers = [col.strip() for col in df_vendor_master.columns if isinstance(col, str)]
            header_obj.gsttax_master_headers = gsttax_master_headers  # update only MIRO headers
        if hsn_master_file:
            df_vendor_master = pd.read_excel(hsn_master_file, nrows=0)
            hsn_master_headers = [col.strip() for col in df_vendor_master.columns if isinstance(col, str)]
            header_obj.hsn_master_headers = hsn_master_headers  # update only MIRO headers
        if sac_master_file:
            df_vendor_master = pd.read_excel(sac_master_file, nrows=0)
            sac_master_headers = [col.strip() for col in df_vendor_master.columns if isinstance(col, str)]
            header_obj.sac_master_headers = sac_master_headers  # update only MIRO headers
        # print(header_obj)
        header_obj.save()  # save updated fields

        return JsonResponse(
            {
                "status": "success",
                "message": "Headers uploaded successfully!",
                
            }
        )
    

@login_required
def mapping_configuration_view(request):
    company = request.user.company_code  # This is a CompanyDetails instance
    header_obj = Header.objects.filter(company=company).first()

    po_headers = header_obj.po_header if header_obj else []
    miro_headers = header_obj.miro_header if header_obj else []
    # se_headers = header_obj.se_headers if header_obj else []
    vendorerp_headers = header_obj.vendor_master_header if header_obj else []
    wholdtax_master_headers = header_obj.wholdtax_master_headers if header_obj else []
    gsttax_master_headers = header_obj.gsttax_master_headers if header_obj else []
    hsn_master_headers = header_obj.hsn_master_headers if header_obj else []
    sac_master_headers = header_obj.sac_master_headers if header_obj else []


    # po_headers = ['po_headers1','po_headers2','po_headers1','po_headers2']
    # miro_headers =  ['miro_headers1','miro_headers2','miro_headers1','miro_headers2']
    se_headers =  ['miro_headers1','miro_headers2','miro_headers1','miro_headers2']
    item_master_headers =  ['item_master_headers1','item_master_headers2','item_master_headers3','item_master_headers4']
    

    # Fetch existing mappings (to pre-select dropdowns)
    # existing_mappings = MappingConfiguration.objects.filter(user=request.user)
    # existing_map_dict = {(m.system_variable, m.source): m.mapped_header for m in existing_mappings}

    vendor_system_variables = [
        "VendorName", "VendorCode", "GSTNo", "LDCNo.",
        "LDCLimit", "LDCStartDate", "LDCEndDate",
        "LDCWTCode", "Blocked(Y/N)", "MSMERegistered(Y/N)",
        "MSMENumber"
    ]
    additional_var = ['variable1', 'varaiable2', 'variable3', 'varaiable4', 'variable5', 'varaiable6', 'variable7', 'varaiable8', 'variable9']
    item_system_variables = ["Item_Number", "Item_Description", "HSN_Code"]
    wholdtax_system_variables = ["WTaxode", "WHoldTaxRate", "LDCNo", "LDCRate"]
    gsttax_system_variables = ["GstTaxcode", "IgstRate", "CgstRate", "SgstRate", "BC_IC", "FCM_RCM"]
    hsn_system_variables = ["HSNcode", "HSNDescription", "CgstRate", "SgstRate", "Igst", "BC_IC"]
    sac_system_variables = ["SACTaxcode", "SACDescription", "TaxRate", "BC_IC", "FCM_RCM"]
    ocr_source = ['BillingAddress','BillingAddressRecipient','Currency','CustomerName','Cutomer Gst No.','EwayBill_No','InvoiceDate',
                  'InvoiceId','InvoiceTotal','Irn_No','PurchaseOrder','ShippingAddress','ShippingAddressRecipient','SubTotal','Tax Items',
                  'Tax_Invoice','TotalDiscount','TotalTax','Vendor Gst No.','VendorAddress','VendorAddressRecipient','VendorName']

    system_vars = [var for var in SYSTEM_VARIABLES if var.get("source") == "MIGO"]

    return render(request, "mapping_headers.html", {
        "system_variables": system_vars,
        "po_headers": po_headers,
        "miro_headers": miro_headers,
        "se_headers": se_headers,
        "vendorerp_headers": vendorerp_headers,
        "vendor_system_variables": vendor_system_variables,
        "item_system_variables":item_system_variables,
        'item_master_headers':item_master_headers,
        'sac_system_variables':sac_system_variables,
        'sac_master_headers':sac_master_headers,
        'additional_var':additional_var,
        'wholdtax_master_headers':wholdtax_master_headers,
        'wholdtax_system_variables':wholdtax_system_variables,
        'gsttax_master_headers':gsttax_master_headers,
        'gsttax_system_variables':gsttax_system_variables,
        'hsn_master_headers':hsn_master_headers,
        'hsn_system_variables':hsn_system_variables,
        'ocr_source':ocr_source
        

    })

@csrf_exempt
def get_mapping_data(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    data = json.loads(request.body)
    mapping_type = data.get("type")
    company = request.user.company_code  # This is a CompanyDetails instance
    print(mapping_type)
    if mapping_type == "system_variables":
        mappings = SystemVariableMapping.objects.filter(company=company)
        result = {
            m.system_var: {
                "po_header": m.po_header,
                "miro_header": m.miro_header,
                "se_header": m.se_header,
                "secondary_source": m.secondary_source,
            }
            for m in mappings
        }
        print('system_variables --> ',result)

    elif mapping_type == "vendor_master":
        mappings = VendorMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {
                "VendorName": mappings.VendorName,
                "VendorCode": mappings.VendorCode,
                "GSTNo": mappings.GSTNo,
                "LDCNo.": mappings.LDCNo,
                "LDCLimit": mappings.LDCThreshold,
                "LDCStartDate": mappings.LDCStartDate,
                "LDCEndDate": mappings.LDCEndDate,
                "LDCWTCode": mappings.LDCWTCode,
                "Blocked(Y/N)": mappings.BlockedYN,
                "MSMERegistered(Y/N)": mappings.MSMERegisteredYN,
                "MSMENumber": mappings.MSMENumber,
            }
        else:
            result = {}
        print('vendor_master --> ',result)

    elif mapping_type == "sac_master":
        mappings = SACMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {               
                "SACTaxcode":mappings.saccode,
                "SACDescription": mappings.sacDescription,
                "TaxRate": mappings.taxrate,
                "BC_IC": mappings.block_input,
                "FCM_RCM": mappings.rcm_fc,    
            }
        else:
            result = {}
        print('sac_master --> ',result)

    elif mapping_type == "hsn_master":
        mappings = HsnMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {
                    "HSNcode": mappings.hsncode,
                    "HSNDescription": mappings.hsnDescription,
                    "CgstRate": mappings.cgstrate,
                    "SgstRate": mappings.sgstrate,
                    "Igst": mappings.igstrate,
                    "BC_IC": mappings.block_input,
                }
        else:
            result = {}
        print('hsn_master --> ',result)

    elif mapping_type == "wholdtax_master":
        mappings = withholdingtaxMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {
                    "WTaxode": mappings.wtaxcode,
                    "WHoldTaxRate": mappings.wtaxcoderate,
                    "LDCNo": mappings.ldc,
                    "LDCRate": mappings.ldtrate,
                }
        else:
            result = {}
        print('wholdtax_master --> ',result)

    elif mapping_type == "gsttax_master":
        mappings = gsttaxMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {
                    "GstTaxcode": mappings.gsttaxcode,
                    "IgstRate": mappings.igstrate,
                    "CgstRate": mappings.cgstrate,
                    "SgstRate": mappings.sgstrate,
                    "BC_IC": mappings.bc_ic,
                    "FCM_RCM": mappings.fc_rc,
                }
        else:
            result = {}
        print('gsttax_master --> ',result)
    
    elif mapping_type == "item_master":
        mappings = ItemMastersMapping.objects.filter(company=company).first()
        if mappings:
            result = {
                    "Item_Number": mappings.gsttaxcode,
                    "Item_Description": mappings.igstrate,
                    "HSN_Code": mappings.cgstrate,
                    
                }
        else:
            result = {}
        print('gsttax_master --> ',result)

    # add other master types similarly...

    else:
        return JsonResponse({"error": "Unknown mapping type"}, status=400)

    return JsonResponse({"success": True, "data": result})


@csrf_exempt
@login_required
def save_mappings(request):
    if request.method == "POST":
        data = json.loads(request.body)
        mappings = data.get("mappings", [])
        mappings_ = data.get("mappingss", {})
        mapping_type = data.get("type")
        company = request.user.company_code  # CompanyDetails instance
        print(mapping_type,mappings,mappings_)
        if mapping_type == 'system_variables':
            # Clear previous mappings
            SystemVariableMapping.objects.filter(company=company).delete()

            # Save new mappings
            for mapping in mappings:
                SystemVariableMapping.objects.create(
                    company=company,
                    system_var=mapping.get("system_variable", ""),
                    po_header=mapping.get("po_header", ""),
                    miro_header=mapping.get("migo_header", ""),
                    se_header=mapping.get("se_header", ""),
                    secondary_source=mapping.get("secondary_source", ""),
                    created_at=timezone.now()
                )
            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        elif mapping_type == 'vendor_master':
            # Clear previous mappings
            VendorMastersMapping.objects.filter(company=company).delete()
            VendorMastersMapping.objects.create(
                    company=company,
                    VendorName = mappings_.get("VendorName", ""),
                    VendorCode = mappings_.get("VendorCode", ""),
                    GSTNo = mappings_.get("GSTNo", ""),
                    LDCNo = mappings_.get("LDCNo.", ""),
                    LDCThreshold = mappings_.get("LDCLimit", ""),
                    LDCStartDate = mappings_.get("LDCStartDate", ""),
                    LDCEndDate = mappings_.get("LDCEndDate", ""),
                    LDCWTCode = mappings_.get("LDCWTCode", ""),
                    BlockedYN = mappings_.get("Blocked(Y/N)", ""),
                    MSMERegisteredYN = mappings_.get("MSMERegistered(Y/N)", ""),
                    MSMENumber = mappings_.get("MSMENumber", "")
                    
                )

            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        elif mapping_type == 'wholdtax_master':
            # Clear previous mappings
            withholdingtaxMastersMapping.objects.filter(company=company).delete()
            withholdingtaxMastersMapping.objects.create(
                    company=company,
                    wtaxcode = mappings_.get("WTaxode", ""),
                    wtaxcoderate = mappings_.get("WHoldTaxRate", ""),
                    ldc = mappings_.get("LDCNo", ""),
                    ldtrate = mappings_.get("LDCRate", ""),
                    )
            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        elif mapping_type == 'gsttax_master':
            # Clear previous mappings
            gsttaxMastersMapping.objects.filter(company=company).delete()
            gsttaxMastersMapping.objects.create(
                    company=company,
                    gsttaxcode = mappings_.get("GstTaxcode", ""),
                    igstrate = mappings_.get("IgstRate", ""),
                    cgstrate = mappings_.get("CgstRate", ""),
                    sgstrate = mappings_.get("SgstRate", ""),
                    bc_ic = mappings_.get("BC_IC", ""),
                    fc_rc = mappings_.get("FCM_RCM", ""),
                    )
            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        elif mapping_type == 'hsn_master':
            # print(mappings_)
            # Clear previous mappings
            HsnMastersMapping.objects.filter(company=company).delete()
            HsnMastersMapping.objects.create(
                    company=company,
                    hsncode = mappings_.get("HSNcode", ""),
                    hsnDescription = mappings_.get("HSNDescription", ""),
                    cgstrate = mappings_.get("CgstRate", ""),
                    sgstrate = mappings_.get("SgstRate", ""),
                    igstrate = mappings_.get("Igst", ""),
                    block_input = mappings_.get("BC_IC", ""),
                    )
            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        elif mapping_type == 'sac_master':
            # print(mappings_)
            # Clear previous mappings
            SACMastersMapping.objects.filter(company=company).delete()
            SACMastersMapping.objects.create(
                    company=company,
                    saccode = mappings_.get("SACTaxcode", ""),
                    sacDescription = mappings_.get("SACDescription", ""),
                    taxrate = mappings_.get("TaxRate", ""),
                    block_input = mappings_.get("BC_IC", ""),
                    rcm_fc = mappings_.get("FCM_RCM", ""),
                    )
            return JsonResponse({"status": "success", "message": "Mappings saved successfully"})
        # gsttax_system_variables = ["GstTaxcode", "IgstRate", "CgstRate", "SgstRate", "BC/IC", "FCM/RCM"]


def configurations(request):
    """Render the configuration form page"""
    return render(request, "config_home.html")

@login_required
def additional_varaiables_view(request):
    company = request.user.company_code  # This is a CompanyDetails instance
    header_obj = Header.objects.filter(company=company).first()

    po_headers = header_obj.po_header if header_obj else []
    miro_headers = header_obj.miro_header if header_obj else []
    # se_headers = header_obj.se_headers if header_obj else []

    # po_headers = ['po_headers1','po_headers2','po_headers1','po_headers2']
    # miro_headers =  ['miro_headers1','miro_headers2','miro_headers1','miro_headers2']
    se_headers =  ['miro_headers1','miro_headers2','miro_headers1','miro_headers2']
    vendorerp_headers =  ['vendorerp_headers1','vendorerp_headers2','vendorerp_headers3','vendorerp_headers4']


    # Fetch existing mappings (to pre-select dropdowns)
    # existing_mappings = MappingConfiguration.objects.filter(user=request.user)
    # existing_map_dict = {(m.system_variable, m.source): m.mapped_header for m in existing_mappings}

    
    additional_var = ['variable1', 'variable2', 'variable3', 'variable4',
                       'variable5', 'variable6', 'variable7', 'variable8', 
                       'variable9'
                    ]
    

    return render(request, "additional_variables.html", {
        
        "po_headers": po_headers,
        "miro_headers": miro_headers,
        "se_headers": se_headers,
        "vendorerp_headers": vendorerp_headers,
        'additional_var':additional_var
    })

@csrf_exempt
@login_required
def save_additional_varaiables_view(request):
    if request.method == "POST":
        data = json.loads(request.body)
        print(data)
    

    return JsonResponse({"status": "success", "message": "Mappings saved successfully"})

@login_required
def user_management_view(request):
    users = User.objects.filter(company_code=request.user.company_code)
    return render(request, "users.html", {"users": users})

@csrf_exempt
@login_required
def add_user_ajax(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get("name")
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")
        status = data.get("status", "Active")
        company = request.user.company_code

        if User.objects.filter(email=email).exists():
            return JsonResponse({"success": False, "message": "User with this email already exists."})

        user = User.objects.create_user(
            first_name=name,
            username=email,
            email=email,
            password=password,
            role=role,
            status=status,
            company_code=company
        )
        user.save()
        return JsonResponse({
            "success": True,
            
        })

    return JsonResponse({"success": False, "message": "Invalid request method"})


@login_required
def invoice_display(request):
    context = {}
    # Get data from session
    # api_response = request.session.get('api_response', {})
    # result = api_response.get('result', {})
    # Define the directory where responses are saved
    user = request.user  # Get the logged-in user
    user_index = request.session.get("user_id")
    company = request.user.company_code
    
    # response_dir = os.path.join(settings.MEDIA_ROOT, "responses", user_index)
    response_dir = os.path.join(settings.MEDIA_ROOT, "responses", str(company))
    
    # Get the response file name from the query parameter
    response_file_name = request.GET.get('response_file')
    # print(response_file_name)
    if response_file_name:
        # Construct the full path to the response file
        response_file = os.path.join(response_dir, response_file_name)
        # print(response_file)
        try:
            # Check if the response file exists
            if os.path.exists(response_file):
                # Load the response data from the file
                with open(response_file, "r") as file:
                    api_response = json.load(file)
                    # print(api_response)
                
                # Extract relevant data
                result = api_response.get("result", {})
                # Extract default data
                invoice_data = result.get('Invoice_data', {})
                # print(invoice_data)
                table_data_json = result.get('CHECKS', {}).get('table_data', {}).get('Table_Check_data', '[]')
                table_data = json.loads(table_data_json) if isinstance(table_data_json, str) else table_data_json
                # print(table_data)
                ##tax check table disintegration into 5 tables
                account_check = result.get('CHECKS', {}).get('Account_check', {})
                tax_check = result.get('CHECKS', {}).get('tax_check', {})
                Filinq_status_data = result.get('CHECKS', {}).get('data_from_gst', {}).get('Filing Status', [])
                YES_NO = {'Okay':'YES',
                        'Not Okay': 'NO'}
                YES_NO_ = {'Okay':'NO',
                        'Not Okay': 'YES',
                        'YES':'NO',
                        "NO":"YES"}
                Okay_NOtOkay_ = {'NO':'Okay',
                        'YES':'Not Okay',
                        }
                try:
                    tax_check_companygst_mentioned = {}
                    tax_check_vendorgst_mentioned = {}
                    tax_check_vendorfilingstatus = {}
                    # print(Filinq_status_data)
                    # print('hello--1')
                    # filingstatus_rslt = filingstatus(Filinq_status_data)
                    # print(filingstatus_rslt)
                    tax_check_taxpayertype_filingfrequncy = {}
                    tax_check_correctgstcharged = {}
                    tax_check_RCM_Blockedcredit = {} 
                    tax_check_data = {}

                    tax_check_companygst_mentioned['Is GST No. of the company mentioned on the invoice (When company registered in GST)?'] = tax_check['Company_Gst_mentioned']['status']
                    tax_check_companygst_mentioned['Company GST Number -As per Invoice'] = invoice_data.get('Cutomer Gst No.')
                    tax_check_companygst_mentioned['Company GST Number-As per Masters in WFS'] = ' '
                    tax_check_companygst_mentioned['Is Company GST No. as per invoice & as per Masters matching?'] = ' '

                    gstcharge_stats = account_check['gstnumber_gstcharged']['status']
                    tax_check_vendorgst_mentioned['Is Vendor GST No. mentioned on the invoice (when GST Charged)?'] = tax_check['Vendor_Gst_mentioned']['status']
                    tax_check_vendorgst_mentioned['Vendor GST Number -As per Invoice'] = invoice_data.get('Vendor Gst No.')
                    tax_check_vendorgst_mentioned['Is GST No. of vendor mentioned on the invoice valid as per GST Portal?'] = tax_check['Vendor_Gst_Valid']['status']
                    tax_check_vendorgst_mentioned['Is Vendor GST Status Active on GST Portal?'] = tax_check['Vendor_Gst_Active']['status']
                    tax_check_vendorgst_mentioned['Is GST Charged on invoice (when GST No. of vendor mentioned)?'] = YES_NO.get(gstcharge_stats) 

                    # tax_check_vendorfilingstatus['Is Vendor regular in filing GST(3B) Return?'] = filingstatus_rslt['status']
                    # tax_check_vendorfilingstatus['Filing Status of Previous month'] = filingstatus_rslt['month']
                    # tax_check_vendorfilingstatus['Filing Status - Earlier to Previous month1'] = filingstatus_rslt['month1']
                    # tax_check_vendorfilingstatus['Filing Status - Earlier to Previous month2'] = filingstatus_rslt['month2']

                    tax_check_taxpayertype_filingfrequncy['Vendor Tax Payer Type as per GST Portal'] = tax_check['Vendor_TaxPayer_type']['status']
                    tax_check_taxpayertype_filingfrequncy['Vendor Filing Frequency as per GST Portal'] = tax_check['Vendor_Taxfiliging_Frequency']['status']

                    taxtypestatus = tax_check['tax_type_on_invoice']['status']
                    tax_check_correctgstcharged['Is correct tax type is charged on invoice (CGST&SGST/IGST)?'] = YES_NO.get(taxtypestatus)
                    tax_check_correctgstcharged['Company GST No. (First 2 Digits) (As per invoice)'] = invoice_data.get('Cutomer Gst No.')
                    tax_check_correctgstcharged['Vendor GST No. (First 2 Digits) (As per invoice)'] = invoice_data.get('Vendor Gst No.')

                    rcm_status = account_check['Invoice_RCM-Services']['status']
                    blockedcredit_status = account_check['Invoice_Blocked_Credit']['status']
                    tax_check_RCM_Blockedcredit['Is Invoice covered under RCM'] = YES_NO_.get(rcm_status)
                    tax_check_RCM_Blockedcredit['Reason of coverage under RCM'] = account_check['Invoice_RCM-Services']['Invoice_data']
                    tax_check_RCM_Blockedcredit['Is Invoice covered under Blocked Credit'] = YES_NO_.get(blockedcredit_status)
                    tax_check_RCM_Blockedcredit['Reason of coverage under Blocked credit'] = account_check['Invoice_Blocked_Credit']['Invoice_data']
                    
                    tax_check_data['tax_check_companygst_mentioned'] = tax_check_companygst_mentioned
                    tax_check_data['tax_check_vendorgst_mentioned'] = tax_check_vendorgst_mentioned
                    tax_check_data['tax_check_vendorfilingstatus'] = tax_check_vendorfilingstatus
                    tax_check_data['tax_check_taxpayertype_filingfrequncy'] = tax_check_taxpayertype_filingfrequncy
                    tax_check_data['tax_check_correctgstcharged'] = tax_check_correctgstcharged
                    tax_check_data['tax_check_RCM_Blockedcredit'] = tax_check_RCM_Blockedcredit
                except:
                    pass
                ## account check table disintegration into smaller table
                Checks = {}
                try:
                    try:
                        invoice_vs_gstin_protal = {}
                        company_name = {}
                        company_address = {}

                        company_name['parameter'] = 'Company Name'
                        company_name['As_per_Invoice'] = account_check['Customer_Name']['Invoice_data']
                        company_name['As_per_GST_Portal'] = account_check['Customer_Name']['Gst_Portal']
                        company_name['As_per_GST_Portal_legal'] = result.get('CHECKS', {}).get('data_from_gst', {}).get('customer_gst_data', {}).get('lgnm', None)
                        company_name['Result'] = account_check['Customer_Name']['status']
                        # print('this--1')
                        company_address['parameter'] = 'Company Address'
                        company_address['As_per_Invoice'] = account_check['Customer_Adress']['Invoice_data']
                        company_address['As_per_GST_Portal'] = account_check['Customer_Adress']['Gst_Portal']
                        company_address['Result'] = account_check['Customer_Adress']['status']
                        # print('this--2')
                        invoice_vs_gstin_protal['company_name'] = company_name
                        invoice_vs_gstin_protal['company_address'] = company_address
                        # print('this--3')
                        Checks['invoice_vs_gstin_protal'] = invoice_vs_gstin_protal
                    except Exception as e:
                        print(f"Error--1 : {str(e)}")

                    try:
                        invoice_validations = {}
                        invoice_complete = {}
                        invoice_valid = {}
                        invoice_Date = {}
                        invoice_No = {}
                        invoice_pre_year = {}
                        Comapny_gst_no_mentioned = {}
                        Gst_charged = {}
                        Vendor_gst_no_mentioned = {}
                        gst_type = {}
                        rcm_covered = {}
                        blocked_credit = {}
                        try:
                            invoice_complete['parameter'] = 'Invoice Complete?'
                            invoice_complete['Result'] = account_check['Complete_Invoice']['status']
                            invoice_complete['As_per_Invoice'] = 'Supplier Name, PAN, Customer Name, Customer Address, GST/PAN, Bill No., Bill Date, Basic Value, Total Value'
                            invoice_validations['invoice_complete'] = invoice_complete
                        except Exception as e:
                            print(f"Error--2 : {str(e)}")
                        try:
                            invoice_valid['parameter'] = 'Invoice Valid ?'
                            invoice_valid['Result'] = account_check['valid_invoice']['status']
                            invoice_valid['As_per_Invoice'] = 'Should not mention - PI/Estimate/Commercial Invoice/Supply invoice/Challan'
                            invoice_validations['invoice_valid'] = invoice_valid
                        except Exception as e:
                            print(f"Error--3 : {str(e)}")
                        try:
                            okay1 = account_check['Invoice_Date']['status']
                            date_ = account_check['Invoice_Date']['Invoice_data']
                            invoice_Date['parameter'] = 'Invoice Date'
                            invoice_Date['Result'] = YES_NO.get(okay1)
                            invoice_Date['As_per_Invoice'] = f'Invoice Date: {date_}'
                            invoice_validations['invoice_Date'] = invoice_Date
                        except Exception as e:
                            print(f"Error---4 : {str(e)}")
                        try:
                            invoice_ = account_check['Invoice_Number']['Invoice_data']
                            okay2 = account_check['Invoice_Number']['status']
                            invoice_No['parameter'] = 'Invoice No.'
                            invoice_No['Result'] = YES_NO.get(okay2)
                            invoice_No['As_per_Invoice'] = f'Invoice No.: {invoice_}'
                            invoice_validations['invoice_No'] = invoice_No
                        except Exception as e:
                            print(f"Error---5 : {str(e)}")
                        try:
                            date_ = account_check['Invoice_Date']['Invoice_data']
                            pre_yr_stst = account_check['Pre_year']['status']
                            # print(pre_yr_stst)
                            invoice_pre_year['parameter'] = 'Invoice of current Year'
                            invoice_pre_year['Result'] = YES_NO_.get(pre_yr_stst)
                            invoice_pre_year['As_per_Invoice'] = f'Invoice Date: {date_}'
                            invoice_validations['invoice_pre_year'] = invoice_pre_year
                        except Exception as e:
                            print(f"Error---6 : {str(e)}")
                        try:
                            Comapny_gst_no_mentioned['parameter'] = 'GST No. of Company Mentioned?'
                            Comapny_gst_no_mentioned['Result'] = tax_check['Company_Gst_mentioned']['status']
                            Comapny_gst_no_mentioned['As_per_Invoice'] = invoice_data.get('Cutomer Gst No.')
                            invoice_validations['Comapny_gst_no_mentioned'] = Comapny_gst_no_mentioned
                        except Exception as e:
                            print(f"Error---7 : {str(e)}")
                        try:
                            Gst_charged_stst = account_check['gstnumber_gstcharged']['status']
                            # print(Gst_charged_stst)
                            Gst_charged['parameter'] = 'GST Charged on invoice? (When vendor registered)'
                            Gst_charged['Result'] = YES_NO.get(Gst_charged_stst)
                            Gst_charged['As_per_Invoice'] = ''
                            invoice_validations['Gst_charged'] = Gst_charged
                        except Exception as e:
                            print(f"Error---8 : {str(e)}")
                        try:
                            Vendor_gst_no_mentioned['parameter'] = 'GST No. of Vendor Mentioned? (When GST Charged)'
                            Vendor_gst_no_mentioned['Result'] = tax_check['Vendor_Gst_mentioned']['status']
                            Vendor_gst_no_mentioned['As_per_Invoice'] = invoice_data.get('Vendor Gst No.')
                            invoice_validations['Vendor_gst_no_mentioned'] = Vendor_gst_no_mentioned
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            taxtypestatus = tax_check['tax_type_on_invoice']['status']
                            gst_type['parameter'] = 'GST Type -  Correctly Charged'
                            gst_type['Result'] = YES_NO.get(taxtypestatus)
                            gst_type['As_per_Invoice'] = ''
                            invoice_validations['gst_type'] = gst_type
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            rcm_status = account_check['Invoice_RCM-Services']['status']
                            # print(rcm_status)
                            rcm_covered['parameter'] = 'Invoice - Not Covered under RCM?'
                            rcm_covered['Result'] = YES_NO_.get(rcm_status)
                            rcm_covered['As_per_Invoice'] = account_check['Invoice_RCM-Services']['Invoice_data']
                            invoice_validations['rcm_covered'] = rcm_covered
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            blockedcredit_status = account_check['Invoice_Blocked_Credit']['status']
                            # print(blockedcredit_status)
                            blocked_credit['parameter'] = 'Invoice - Not Covered under Blocked Credit?'
                            blocked_credit['Result'] =YES_NO.get(blockedcredit_status)
                            blocked_credit['As_per_Invoice'] = account_check['Invoice_Blocked_Credit']['Invoice_data']
                            invoice_validations['blocked_credit'] = blocked_credit
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        Checks['invoice_validations'] = invoice_validations
                    except:
                        pass
                    try:
                        gst_portal_check = {}
                        vendor_gst_valid = {}
                        vendor_gst_active = {}
                        vendor_3B_filingstatus = {}
                        vendor_3B_filingstatus1 = {}
                        vendor_3B_filingstatus2 = {}
                        vendor_3B_filingstatus3 = {}
                        vendor_gstr1_filingstatus = {}
                        vendor_gstr1_filingstatus1 = {}
                        vendor_gstr1_filingstatus2 = {}
                        vendor_gstr1_filingstatus3 = {}
                        vendor_taxpayer_type = {}
                        vendor_filing_frquncy = {}
                        try:
                            vendor_gst_valid['parameter'] = 'GST No. of Vendor valid as per GSTN?'
                            vendor_gst_valid['Result'] = tax_check['Vendor_Gst_Valid']['status']
                            gst_portal_check['vendor_gst_valid'] = vendor_gst_valid
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            vendor_gst_active['parameter'] = 'GST No. of Vendor Active on GSTN?'
                            vendor_gst_active['Result'] = tax_check['Vendor_Gst_Active']['status']
                            gst_portal_check['vendor_gst_active'] = vendor_gst_active
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")

                        try:
                            tax_check['Vendor_Taxfiliging_Frequency']['status']
                            vendor_taxpayer_type['parameter'] = 'Vendor Tax Payer Type'
                            vendor_taxpayer_type['Result'] = tax_check['Vendor_TaxPayer_type']['status']
                            gst_portal_check['vendor_taxpayer_type'] = vendor_taxpayer_type
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            
                            vendor_filing_frquncy['parameter'] = 'Vendor Tax Payer - Filing Frequency'
                            vendor_filing_frquncy['Result'] = tax_check['Vendor_Taxfiliging_Frequency']['status']
                            gst_portal_check['vendor_filing_frquncy'] = vendor_filing_frquncy
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            filingstatus_rslt_3b , filingstatus_rslt_gstr1, df_gstr1, df_3b = filingstatus(Filinq_status_data)
                            df_gstr1_html= df_gstr1.to_html(index=False, classes="table table-bordered")
                            df_3b_html= df_3b.to_html(index=False, classes="table table-bordered")
                            ##gstr3b
                            vendor_3B_filingstatus['parameter'] = 'Vendor GSTR 3B Filing Status'
                            vendor_3B_filingstatus['Result'] = ''
                            gst_portal_check['vendor_3B_filingstatus'] = vendor_3B_filingstatus

                            vendor_3B_filingstatus1['parameter'] = 'Previous Month (Month 1)'
                            vendor_3B_filingstatus1['Result'] = filingstatus_rslt_3b['month']
                            gst_portal_check['vendor_3B_filingstatus1'] = vendor_3B_filingstatus1

                            vendor_3B_filingstatus2['parameter'] = 'Month prior to Month 1 (Month 2)'
                            vendor_3B_filingstatus2['Result'] = filingstatus_rslt_3b['month1']
                            gst_portal_check['vendor_3B_filingstatus2'] = vendor_3B_filingstatus2

                            vendor_3B_filingstatus3['parameter'] = 'Month prior to Month 2 (Month 3)'
                            vendor_3B_filingstatus3['Result'] = filingstatus_rslt_3b['month2']
                            gst_portal_check['vendor_3B_filingstatus3'] = vendor_3B_filingstatus3
                            ##gstr1
                            vendor_gstr1_filingstatus['parameter'] = 'Vendor GSTR 1 Filing Status'
                            vendor_gstr1_filingstatus['Result'] = ''
                            gst_portal_check['vendor_gstr1_filingstatus'] = vendor_gstr1_filingstatus

                            vendor_gstr1_filingstatus1['parameter'] = 'Previous Month (Month 1)'
                            vendor_gstr1_filingstatus1['Result'] = filingstatus_rslt_gstr1['month']
                            gst_portal_check['vendor_gstr1_filingstatus1'] = vendor_gstr1_filingstatus1

                            vendor_gstr1_filingstatus2['parameter'] = 'Month prior to Month 1 (Month 2)'
                            vendor_gstr1_filingstatus2['Result'] = filingstatus_rslt_gstr1['month1']
                            gst_portal_check['vendor_gstr1_filingstatus2'] = vendor_gstr1_filingstatus2

                            vendor_gstr1_filingstatus3['parameter'] = 'Month prior to Month 2 (Month 3)'
                            vendor_gstr1_filingstatus3['Result'] = filingstatus_rslt_gstr1['month2']
                            gst_portal_check['vendor_gstr1_filingstatus3'] = vendor_gstr1_filingstatus3
                        except Exception as e:
                            gst_portal_check = {}
                            print(f"Error while loading response: {str(e)}")
                        
                        Checks['gst_portal_check'] = gst_portal_check
                    except Exception as e:
                        print(f"Error while loading response: {str(e)}")
                    try:
                        income_tax_check = {}
                        vendor_pan_active = {}
                        vendor_pan_adhar_linked = {}
                        vendor_206AB = {}

                        try:
                            pan_stats = tax_check['Vendor_Pan_Active']['status']
                            vendor_pan_active['parameter'] = 'Vendor PAN Active'
                            vendor_pan_active['Result'] = YES_NO.get(pan_stats)
                            income_tax_check['vendor_pan_active'] = vendor_pan_active
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            pan_adhar_stats = tax_check['Vendor_Pan-Adhar_Linked']['status']
                            # print(pan_adhar_stats)
                            vendor_pan_adhar_linked['parameter'] = 'Vendor Aadhar & PAN linked (For Individual & Proprietor)'
                            vendor_pan_adhar_linked['Result'] = YES_NO.get(pan_adhar_stats)
                            income_tax_check['vendor_pan_adhar_linked'] = vendor_pan_adhar_linked
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        try:
                            vendor_206AB_stst = tax_check['Vendor_206AB']['status']
                            vendor_206AB['parameter'] = 'Vendor Defaulter u/s 206AB'
                            vendor_206AB['Result'] = YES_NO_.get(vendor_206AB_stst)
                            income_tax_check['vendor_206AB'] = vendor_206AB
                        except Exception as e:
                            print(f"Error while loading response: {str(e)}")
                        Checks['income_tax_check'] = income_tax_check
                    except Exception as e:
                        print(f"Error while loading response: {str(e)}")
                except:
                    pass

                

                try:
                    ##table data
                    Table_Data = {}
                    
                    tabledata_,check_2,check_3 = Table_data(table_data, invoice_data)
                    Table_Data['tabledata_'] = tabledata_
                    Table_Data['check_2'] = check_2
                    Table_Data['check_3'] = check_3
                    # print('this---2')
                    # print(Table_Data)
                except:
                    pass
                ##table_data vs grn data
                # print('this---3')
                grn_vs_inoice = {}
                try:
                    invoice_table,grn_data = InvoiceTable_vs_GrnTable(invoice_data,user_index)
                    # print('this---4')
                    # print(invoice_table,grn_data)
                    
                    if invoice_table[0] == 200:
                        grn_vs_inoice['invoice_data'] = invoice_table[1]
                        grn_vs_inoice['invoice_message'] = ''
                    else:
                        grn_vs_inoice['invoice_data'] = ''
                        grn_vs_inoice['invoice_message'] = invoice_table[1]
                    if grn_data[0] == 200:
                        grn_vs_inoice['grn_data'] = grn_data[1]
                        grn_vs_inoice['grn_message'] = ''
                    else:
                        grn_vs_inoice['grn_data'] = ''
                        grn_vs_inoice['grn_message'] = grn_data[1]
                except:
                    pass
                
                try:
                    invoice_table_vs_grn_data = Invoicetable_vs_Grntable_compare(invoice_data,user_index)
                    # print(invoice_table_vs_grn_data)
                except:
                    invoice_table_vs_grn_data = {}
                # print('this---5')
                # Pass data to context for rendering
                
                try:
                    # context = {
                    #     'active_tab': 'Invoice_data',
                    #     'invoice_data': invoice_data,
                    #     'Tax_check': tax_check_data,
                    #     'gst_data': result.get('CHECKS', {}).get('data_from_gst', {}),
                    #     'table_data' : Table_Data,
                    #     'Checks': Checks,
                    #     # 'Account_check':account_check_data,
                    #     'Filinq_frequency' : result.get('CHECKS', {}).get('data_from_gst', {}).get('Filing Frequency', []),
                    #     'Filinq_status' : Filinq_status_data,
                    #     'df_gstr1_html' : df_gstr1_html,
                    #     'df_3b_html': df_3b_html,
                    #     'grn_vs_invoice' : grn_vs_inoice,
                    #     'keys_with_tooltip': ['invoice_complete', 'invoice_valid'],
                    #     '2b_olive_color' : ['YES', 'Filed', 'Regular', 'Monthly', 'Okay'],
                    #     'Invoicetable_vs_Grntable_compare':invoice_table_vs_grn_data,
                        

                    #     # 'Filinq_status' : result.get('CHECKS', {}).get('data_from_gst', {}).get('Filing Status', [])
                    # }

                    context = {
                        'active_tab': 'Invoice_data',
                        'invoice_data': invoice_data if 'invoice_data' in locals() else {},
                        'Tax_check': tax_check_data if 'tax_check_data' in locals() else {},
                        'gst_data': result.get('CHECKS', {}).get('data_from_gst', {}),
                        'table_data': Table_Data if 'Table_Data' in locals() else {},
                        'Checks': Checks if 'Checks' in locals() else {},
                        'Filinq_frequency': result.get('CHECKS', {}).get('data_from_gst', {}).get('Filing Frequency', {}),
                        'Filinq_status': Filinq_status_data if 'Filinq_status_data' in locals() else {},
                        'df_gstr1_html': df_gstr1_html if 'df_gstr1_html' in locals() else '',
                        'df_3b_html': df_3b_html if 'df_3b_html' in locals() else '',
                        'grn_vs_invoice': grn_vs_inoice if 'grn_vs_inoice' in locals() else {},
                        'keys_with_tooltip': ['invoice_complete', 'invoice_valid'],
                        '2b_olive_color': ['YES', 'Filed', 'Regular', 'Monthly', 'Okay'],
                        'Invoicetable_vs_Grntable_compare': invoice_table_vs_grn_data if 'invoice_table_vs_grn_data' in locals() else {},
                    }

                    # print(context['Checks'])
                except Exception as e:
                    print(f"Error while loading response: {str(e)}")
                # print('this---6')
                # print(context)
            else:
                context["message"] = f"No response file found for: {response_file_name}"
        except Exception as e:
            context["message"] = f"Error while loading response: {str(e)}"
    else:
        context["message"] = "No response file specified."
    
    
    return render(request, 'invoice_display.html', context)

def get_vendor_code(request):
    gst = request.GET.get("gst")
    company = request.user.company_code

    vendor = VendorMastersData.objects.filter(company_id=company, GSTNo=gst).first()

    if vendor:
        return JsonResponse({"status": "found", "vendor_code": vendor.VendorCode})
    else:
        return JsonResponse({"status": "not_found"})
    
def process_incoming_file(response,company,invoice_path,unique_name,invoice_key=None):
    try:
        api_response = response.json()
        # generate unique key once per invoice
        if not invoice_key:
            invoice_key = uuid.uuid4() 
        # concept to park invoices if any field is missing
        invoice_data = api_response.get("result", {}).get('Invoice_data', {})
        # print(invoice_data)

        vendor_gst = invoice_data.get('Vendor Gst No.')
        inv_number = invoice_data.get('InvoiceId')
        vendor_code = None  # ✅ Initialize first

        vendor_master_data = VendorMastersData.objects.filter(company_id=company, GSTNo=vendor_gst).first()

        if vendor_master_data:
            
            vendor_code = vendor_master_data.VendorCode
            print("Incoming invoice is for vendor-->",vendor_code)
            inv_number_already_exist = InvoiceSummary.objects.filter(company_id=company, VendorCode=vendor_code, InvoiceNo=inv_number).first()
            if inv_number_already_exist:
                message = f"This is Duplicate Invoice as Invoice Number {inv_number} for vendor {vendor_code} is already submitted"
                print(message)
                MissingDataInvoices.objects.update_or_create(
                company=company,
                InvNo=str(invoice_data.get('InvoiceId', '')),
                defaults={
                    "VendorGst": invoice_data.get('Vendor Gst No.', ''),
                    "InvDate": invoice_data.get('InvoiceDate', ''),
                    "VendorName": invoice_data.get('VendorAddressRecipient') or invoice_data.get('VendorName'),
                    "VendorCode": vendor_code,
                    "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
                    "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
                    "TotalTax": str(invoice_data.get('TotalTax', '')),
                    "BasicAmount": str(invoice_data.get('SubTotal', '')),
                    "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
                    "path": invoice_path,                          # ✅ corrected field name
                    "InvoiceGroupKey": invoice_key,
                    "unique_name": unique_name,                     # ✅ corrected field name
                    "message": message,
                    "api_response": api_response
                    }
                )
            else:
                required_fields = [
                'Cutomer Gst No.',
                'Vendor Gst No.',
                'SubTotal',
                'InvoiceId',
                'TotalTax',
                'InvoiceTotal',
                'Tax Items'
                ]
                for field in required_fields:
                    print(field, invoice_data.get(field))

                print(vendor_code)
            
                missing_values = any(
                    not invoice_data.get(field) or str(invoice_data.get(field)).lower() == 'none'
                    for field in required_fields
                )
                print(missing_values)

                if missing_values:
                    print('some mandatory fields are missing')
                    PendingInvoices.objects.update_or_create(
                        company=company,
                        InvNo=str(invoice_data.get('InvoiceId', '')),
                        defaults={
                            "VendorGst": invoice_data.get('Vendor Gst No.', ''),
                            "InvDate": invoice_data.get('InvoiceDate', ''),
                            "VendorName": invoice_data.get('VendorName') or invoice_data.get('VendorAddressRecipient'),
                            "VendorCode": vendor_code or '',
                            "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
                            "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
                            "TotalTax": str(invoice_data.get('TotalTax', '')),
                            "BasicAmount": str(invoice_data.get('SubTotal', '')),
                            "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
                            "path": invoice_path,
                            "InvoiceGroupKey": invoice_key,                          # ✅ corrected field name
                            "unique_name": unique_name,                     # ✅ corrected field name
                            "api_response": api_response
                        }
                    )
                else:
                    save_processed_invoice(api_response, invoice_path, unique_name, company, invoice_key)
        else:
            required_fields = [
                'Cutomer Gst No.',
                'Vendor Gst No.',
                'SubTotal',
                'InvoiceId',
                'TotalTax',
                'InvoiceTotal',
                'Tax Items'
            ]
            for field in required_fields:
                print(field, invoice_data.get(field))

            print(vendor_code)
        
            missing_values = any(
                not invoice_data.get(field) or str(invoice_data.get(field)).lower() == 'none'
                for field in required_fields
            )
            print(missing_values)

            if missing_values:
                print('some mandatory fields are missing')
                PendingInvoices.objects.update_or_create(
                    company=company,
                    InvNo=str(invoice_data.get('InvoiceId', '')),
                    defaults={
                        "VendorGst": invoice_data.get('Vendor Gst No.', ''),
                        "InvDate": invoice_data.get('InvoiceDate', ''),
                        "VendorName": invoice_data.get('VendorName') or invoice_data.get('VendorAddressRecipient'),
                        "VendorCode": vendor_code or '',
                        "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
                        "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
                        "TotalTax": str(invoice_data.get('TotalTax', '')),
                        "BasicAmount": str(invoice_data.get('SubTotal', '')),
                        "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
                        "path": invoice_path,                          # ✅ corrected field name
                        "InvoiceGroupKey": invoice_key,
                        "unique_name": unique_name,                     # ✅ corrected field name
                        "api_response": api_response
                    }
                )
            else:
                message = f"This is Invoice has Vendor GSt but not found any Vendor code against captured GST Number {invoice_data.get('Vendor Gst No.', '')}"
                print(message)
                MissingDataInvoices.objects.update_or_create(
                company=company,
                InvNo=str(invoice_data.get('InvoiceId', '')),
                defaults={
                    "VendorGst": invoice_data.get('Vendor Gst No.', ''),
                    "InvDate": invoice_data.get('InvoiceDate', ''),
                    "VendorName": invoice_data.get('VendorAddressRecipient') or invoice_data.get('VendorName'),
                    "VendorCode": vendor_code,
                    "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
                    "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
                    "TotalTax": str(invoice_data.get('TotalTax', '')),
                    "BasicAmount": str(invoice_data.get('SubTotal', '')),
                    "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
                    "path": invoice_path,                          # ✅ corrected field name
                    "InvoiceGroupKey": invoice_key,
                    "unique_name": unique_name,                     # ✅ corrected field name
                    "message": message,
                    "api_response": api_response
                    }
                )
    except:
        pass
            
##          
def process_invoice(invoice_path, unique_name, company):
    """ Function to process each invoice asynchronously """
    try:
        url = "https://ngtechocr.azurewebsites.net/process-invoice-withchecks-updated-splitting"
        user_id = "BC_User1"
        password = "1234@India"
        files = {'pdf_file': open(invoice_path, 'rb')}
        data = {'user_id': user_id, 'password': password, 'App': 'WFS'}

        response = requests.post(url, files=files, data=data)
        files['pdf_file'].close()  # Close file after request

        if response.status_code == 200:
            process_incoming_file(response,company,invoice_path,unique_name)
        else:
            print(f"Error processing {unique_name}: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Exception: {str(e)}")        

# def process_invoice(invoice_path, unique_name, company):
#     """ Function to process each invoice asynchronously """
#     try:
#         url = "https://ngtechocr.azurewebsites.net/process-invoice-withchecks-updated-splitting"
#         user_id = "BC_User1"
#         password = "1234@India"
#         files = {'pdf_file': open(invoice_path, 'rb')}
#         data = {'user_id': user_id, 'password': password, 'App': 'WFS'}

#         response = requests.post(url, files=files, data=data)
#         files['pdf_file'].close()  # Close file after request

#         if response.status_code == 200:
#             api_response = response.json()
#             # generate unique key once per invoice
#             invoice_key = uuid.uuid4() 
#             # concept to park invoices if any field is missing
#             invoice_data = api_response.get("result", {}).get('Invoice_data', {})
#             # print(invoice_data)

#             vendor_gst = invoice_data.get('Vendor Gst No.')
#             inv_number = invoice_data.get('InvoiceId')
#             vendor_code = None  # ✅ Initialize first

#             vendor_master_data = VendorMastersData.objects.filter(company_id=company, GSTNo=vendor_gst).first()

#             if vendor_master_data:
                
#                 vendor_code = vendor_master_data.VendorCode
#                 print("Incoming invoice is for vendor-->",vendor_code)
#                 inv_number_already_exist = InvoiceSummary.objects.filter(company_id=company, VendorCode=vendor_code, InvoiceNo=inv_number).first()
#                 if inv_number_already_exist:
#                     message = f"This is Duplicate Invoice as Invoice Number {inv_number} for vendor {vendor_code} is already submitted"
#                     print(message)
#                     MissingDataInvoices.objects.update_or_create(
#                     company=company,
#                     InvNo=str(invoice_data.get('InvoiceId', '')),
#                     defaults={
#                         "VendorGst": invoice_data.get('Vendor Gst No.', ''),
#                         "InvDate": invoice_data.get('InvoiceDate', ''),
#                         "VendorName": invoice_data.get('VendorAddressRecipient') or invoice_data.get('VendorName'),
#                         "VendorCode": vendor_code,
#                         "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
#                         "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
#                         "TotalTax": str(invoice_data.get('TotalTax', '')),
#                         "BasicAmount": str(invoice_data.get('SubTotal', '')),
#                         "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
#                         "path": invoice_path,                          # ✅ corrected field name
#                         "InvoiceGroupKey": invoice_key,
#                         "unique_name": unique_name,                     # ✅ corrected field name
#                         "message": message,
#                         "api_response": api_response
#                         }
#                     )
#                 else:
#                     required_fields = [
#                     'Cutomer Gst No.',
#                     'Vendor Gst No.',
#                     'SubTotal',
#                     'InvoiceId',
#                     'TotalTax',
#                     'InvoiceTotal',
#                     'Tax Items'
#                     ]
#                     for field in required_fields:
#                         print(field, invoice_data.get(field))

#                     print(vendor_code)
                
#                     missing_values = any(
#                         not invoice_data.get(field) or str(invoice_data.get(field)).lower() == 'none'
#                         for field in required_fields
#                     )
#                     print(missing_values)

#                     if missing_values:
#                         print('some mandatory fields are missing')
#                         PendingInvoices.objects.update_or_create(
#                             company=company,
#                             InvNo=str(invoice_data.get('InvoiceId', '')),
#                             defaults={
#                                 "VendorGst": invoice_data.get('Vendor Gst No.', ''),
#                                 "InvDate": invoice_data.get('InvoiceDate', ''),
#                                 "VendorName": invoice_data.get('VendorName') or invoice_data.get('VendorAddressRecipient'),
#                                 "VendorCode": vendor_code or '',
#                                 "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
#                                 "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
#                                 "TotalTax": str(invoice_data.get('TotalTax', '')),
#                                 "BasicAmount": str(invoice_data.get('SubTotal', '')),
#                                 "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
#                                 "path": invoice_path,
#                                 "InvoiceGroupKey": invoice_key,                          # ✅ corrected field name
#                                 "unique_name": unique_name,                     # ✅ corrected field name
#                                 "api_response": api_response
#                             }
#                         )
#                     else:
#                         save_processed_invoice(api_response, invoice_path, unique_name, company, invoice_key)
#             else:
#                 required_fields = [
#                     'Cutomer Gst No.',
#                     'Vendor Gst No.',
#                     'SubTotal',
#                     'InvoiceId',
#                     'TotalTax',
#                     'InvoiceTotal',
#                     'Tax Items'
#                 ]
#                 for field in required_fields:
#                     print(field, invoice_data.get(field))

#                 print(vendor_code)
            
#                 missing_values = any(
#                     not invoice_data.get(field) or str(invoice_data.get(field)).lower() == 'none'
#                     for field in required_fields
#                 )
#                 print(missing_values)

#                 if missing_values:
#                     print('some mandatory fields are missing')
#                     PendingInvoices.objects.update_or_create(
#                         company=company,
#                         InvNo=str(invoice_data.get('InvoiceId', '')),
#                         defaults={
#                             "VendorGst": invoice_data.get('Vendor Gst No.', ''),
#                             "InvDate": invoice_data.get('InvoiceDate', ''),
#                             "VendorName": invoice_data.get('VendorName') or invoice_data.get('VendorAddressRecipient'),
#                             "VendorCode": vendor_code or '',
#                             "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
#                             "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
#                             "TotalTax": str(invoice_data.get('TotalTax', '')),
#                             "BasicAmount": str(invoice_data.get('SubTotal', '')),
#                             "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
#                             "path": invoice_path,                          # ✅ corrected field name
#                             "InvoiceGroupKey": invoice_key,
#                             "unique_name": unique_name,                     # ✅ corrected field name
#                             "api_response": api_response
#                         }
#                     )
#                 else:
#                     message = f"This is Invoice has Vendor GSt but not found any Vendor code against captured GST Number {invoice_data.get('Vendor Gst No.', '')}"
#                     print(message)
#                     MissingDataInvoices.objects.update_or_create(
#                     company=company,
#                     InvNo=str(invoice_data.get('InvoiceId', '')),
#                     defaults={
#                         "VendorGst": invoice_data.get('Vendor Gst No.', ''),
#                         "InvDate": invoice_data.get('InvoiceDate', ''),
#                         "VendorName": invoice_data.get('VendorAddressRecipient') or invoice_data.get('VendorName'),
#                         "VendorCode": vendor_code,
#                         "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
#                         "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
#                         "TotalTax": str(invoice_data.get('TotalTax', '')),
#                         "BasicAmount": str(invoice_data.get('SubTotal', '')),
#                         "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
#                         "path": invoice_path,                          # ✅ corrected field name
#                         "InvoiceGroupKey": invoice_key,
#                         "unique_name": unique_name,                     # ✅ corrected field name
#                         "message": message,
#                         "api_response": api_response
#                         }
#                     )
            
            
#         else:
#             print(f"Error processing {unique_name}: {response.status_code} - {response.text}")
    
#     except Exception as e:
#         print(f"Exception: {str(e)}")

def save_processed_invoice(api_response,invoice_path, unique_name, company, invoice_key):
    try:
        data_gathering(api_response, company, unique_name, invoice_path, invoice_key)
        all_okay_,api_response_ = all_okay(api_response)
        # Save API response in a JSON file
        okay_notokay = all_okay_['status']
        okay_message = all_okay_['message']
        # print(okay_message)
        okay_message_ = ''
        if not okay_message: 
            pass
        else:
            for mess in okay_message:
                # print(mess)
                okay_message_ = okay_message_ + ' ' + mess
    
        response_dir = os.path.join(settings.MEDIA_ROOT, "responses", str(company))
        os.makedirs(response_dir, exist_ok=True)  # Ensure directory exists

        response_file = os.path.join(response_dir, f"{unique_name}.json")
        with open(response_file, 'w') as f:
            json.dump(api_response, f, indent=4)

    except Exception as e:
        print("An error occurred at top level:", e)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Save invoice details to DB
    save_invoice_detail(
        company=company,
        file_name=unique_name,
        upload_date=timestamp,
        path=invoice_path,
        okay_status=okay_notokay,
        okay_message=okay_message,
        status='waiting'
    )
    return True

def save_invoice_detail(company, file_name, upload_date, path, okay_status=None, okay_message=None, status='waiting'):
    """
    Saves or updates the invoice details for a user.

    Args:
        user (User): The user associated with the invoice.
        file_name (str): The name of the file.
        path (str): The full path of the file.
        okay_status (str, optional): The status of the invoice. Defaults to None.
        okay_message (str, optional): The message related to the invoice. Defaults to None.
        status (str, optional): The status of the invoice. Defaults to 'waiting'.
    """
    
    try:
        # Create or update the invoice detail
        invoice, created = InvoiceDetail.objects.update_or_create(
            company=company,
            file_name=file_name,
            defaults={
                'upload_date':upload_date,
                'path': path,
                'okay_status': okay_status,
                'okay_message': okay_message,
                'status': status,
            }
        )
        if created:
            print(f"Invoice '{file_name}' created ")
        else:
            print(f"Invoice '{file_name}' updated ")
    except Exception as e:
        print(f"Error saving invoice '{file_name}': {e}")

@login_required
def upload_invoice(request):
    """ Upload invoices and process them in the background using threading """
    if request.method == 'POST' and request.FILES.getlist('files'):
        
        
        company = request.user.company_code

        invoice_dir = os.path.join(settings.MEDIA_ROOT, "invoices", str(company))
        os.makedirs(invoice_dir, exist_ok=True)

        uploaded_files = request.FILES.getlist('files')

        for uploaded_file in uploaded_files:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_name = f"{timestamp}_{uploaded_file.name}"
            invoice_path = os.path.join(invoice_dir, unique_name)

            with default_storage.open(invoice_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            # **Start a new thread for processing**
            threading.Thread(target=process_invoice, args=(invoice_path, unique_name, company)).start()

        # Redirect immediately to avoid waiting
        
        return redirect('uploader_dashboard')

    return render(request, 'upload_invoice.html', )

@login_required
def show_invoices(request):
    # Default filter is "waiting"
    status_filter = request.GET.get('status', 'waiting')
    company = request.user.company_code
    # Query invoices based on the selected status
    if status_filter == 'all':
        # Fetch all invoices for the logged-in user
        invoices = InvoiceDetail.objects.filter(company=company)
    else:
        # Fetch invoices filtered by status for the logged-in user
        invoices = InvoiceDetail.objects.filter(company=company, status=status_filter)

    # Prepare context for rendering
    context = {
        'invoices': invoices,
        'selected_status': status_filter,
        'company':company,
    }
    return render(request, 'show_invoices.html', context)

@login_required
def save_template(request):
    # Check if the Save Template button was clicked
    if request.method == "POST":
        user_index = request.session.get("user_id")
        user = request.user
        try:
            # Get the list of selected files from the POST data
            selected_files = request.POST.get('selected_files', '[]')
            selected_files = json.loads(selected_files)  # Convert JSON string to Python list

            # Perform your desired actions with the selected files
            print("Selected files:", selected_files)

            # Generate the message by processing the selected files
            # message = template_formation(selected_files,user_index,user)
            
            if isinstance(message, str):
                # Wrap the string in a list
                message = [message]

            # Redirect to show_templates with the generated message
            return show_templates(request, message)

        except Exception as e:
            # Handle exceptions
            message = [f"Error: {str(e)}"]
            return show_templates(request, message)
        
@login_required
def show_templates(request, message=[]):
    try:
        user_index = request.session.get("user_id")
        user = request.user
        # Read the first Excel sheet
        file_path_1 = os.path.join(settings.BASE_DIR, 'TemplateData', str(user_index), 'header.xlsx')
        # file_path_1 = 'TemplateData/header.xlsx'
        sheet_1 = pd.read_excel(file_path_1)

        # Read the second Excel sheet
        file_path_2 = os.path.join(settings.BASE_DIR, 'TemplateData', str(user_index), 'Templates.xlsx')
        # file_path_2 = 'TemplateData/Templates.xlsx'
        sheet_2 = pd.read_excel(file_path_2)

        # Convert the dataframes to HTML tables
        sheet_1_html = sheet_1.to_html(index=False)
        sheet_2_html = sheet_2.to_html(index=False)

        # Render the 'save_template.html' template
        return render(request, 'save_template.html', {
            'message': message,
            'sheet_1_html': sheet_1_html,
            'sheet_2_html': sheet_2_html
        })
    except Exception as e:
        
        print("An error occurred:", str(e))
        traceback.print_exc()
        # Handle exceptions
        message =[f"Error: {str(e)}"]
        return render(request, 'save_template.html', {
            'message': message,
            'sheet_1_html': '',
            'sheet_2_html': ''
        })
    
def delete_rows(request):
    if request.method == "POST":
        try:
            selected_files = json.loads(request.POST.get("selected_files", "[]"))
            user = request.user
            user_index = request.session.get("user_id")

            # Fetch invoices matching selected file names
            invoices = InvoiceDetail.objects.filter(file_name__in=selected_files, user=user)

            if not invoices.exists():
                return JsonResponse({"status": "error", "message": "No matching invoices found."})

            # Delete associated PDF files
            for invoice in invoices:
                pdf_path = invoice.path  # Assuming `path` stores the file location
                pdf_name = invoice.file_name
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)  # Delete the file
                # response_dir = os.path.join(settings.MEDIA_ROOT, "responses", user_index)
                response_dir = os.path.join(settings.MEDIA_ROOT, "responses", str(user_index))
                response_file = os.path.join(response_dir, f"{pdf_name}.json")
                # print(response_file)
                if response_file and os.path.exists(response_file):
                    os.remove(response_file)  # Delete the file

            # Delete the invoice records
            deleted_count, _ = invoices.delete()

            return JsonResponse({"status": "success", "message": f"{deleted_count} invoices deleted successfully."})

        except Exception as e:
            return JsonResponse({"status": "error", "message": f"Error: {str(e)}"})

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

@login_required
def pdf_show(request):
    user = request.user  # Get the logged-in user
    user_index = user.id
    company = request.user.company_code
    # print('comapny-->',company)
    # Get the PDF file name from the URL parameter
    response_file = request.GET.get('response_file')
    pdf_path = os.path.join(settings.MEDIA_ROOT, "invoices", str(company), response_file)
    # print(pdf_path)
    # # Define the folder where your PDF files are stored
    # response_dir = os.path.join(settings.MEDIA_ROOT, "invoices")
    # pdf_path = os.path.join(response_dir, response_file)

    # Check if the file exists
    if not os.path.exists(pdf_path):
        raise Http404("PDF file not found.")

    # Pass the URL-relative path to the template
    pdf_url = f"{settings.MEDIA_URL}invoices/{company}/{response_file}"
    # print(pdf_url)

    return render(request, 'invoice_pdf_show.html', {'pdf_name': pdf_url})




def upload_data_view(request):
    context = {}

    if request.method == 'POST':
        data_type = request.POST.get('data_type')
        uploaded_file = request.FILES.get('excel_file')
        company = getattr(request.user, 'company_code', None)
        # print(data_type)
        if not company:
            context['error'] = "User not linked to any company."
            return render(request, 'upload_data.html', context)

        if not uploaded_file:
            context['error'] = "No file uploaded."
            return render(request, 'upload_data.html', context)

        try:
            df = pd.read_excel(uploaded_file)
            df.columns = df.columns.str.strip()
            context['file_content'] = df.head().to_html(classes="table table-bordered", index=False)
            context['data_type'] = data_type

            # Only process saving if type is MIGO
            
            if data_type.lower() == 'migo':
                try:
                    saved_count, skipped_count = 0, 0

                    # Fetch column mapping for VendorCode & DocumentNumber
                    try:
                        vendorcode_header = SystemVariableMapping.objects.get(
                            company=company, system_var='VendorCode'
                        ).miro_header
                        document_header = SystemVariableMapping.objects.get(
                            company=company, system_var='DocumentNumber'
                        ).miro_header
                        inv_num_header = SystemVariableMapping.objects.get(
                            company=company, system_var='SuppInv_no'
                        ).miro_header
                    except SystemVariableMapping.DoesNotExist:
                        context['error'] = "System variable mappings for MIGO not found."
                        return render(request, 'upload_data.html', context)
                    # print(vendorcode_header, document_header)
                    # print(df.columns)
                    # Ensure the Excel file has required columns
                    if vendorcode_header not in df.columns or document_header not in df.columns:
                        context['error'] = f"Excel file missing expected columns: {vendorcode_header}, {document_header}"
                        return render(request, 'upload_data.html', context)
                    # print(vendorcode_header, document_header)
                    # --- Group by document number ---
                    grouped = df.groupby(document_header)
                    # print(grouped)
                    with transaction.atomic():
                        for doc_number, group_df in grouped:
                            document_number = str(doc_number).strip()
                            # print(document_number)
                            # Skip entire group if already exists
                            if OpenGRNData.objects.filter(company=company, document_number=document_number).exists():
                                skipped_count += len(group_df)
                                continue

                            # Common vendor code for this group
                            vendor_code = str(group_df.iloc[0][vendorcode_header]).strip()
                            # Common vendor code for this group
                            inv_num = str(group_df.iloc[0][inv_num_header]).strip()
                            inv_num = re.sub(r'[^A-Za-z0-9]', '', inv_num)
                            # Iterate through each row in this group
                            for _, row in group_df.iterrows():
                                # Convert single row to serializable dict
                                row_data = {col: (str(val) if pd.notna(val) else None) for col, val in row.items()}

                                OpenGRNData.objects.create(
                                    company=company,
                                    vendor_code=vendor_code,
                                    document_number=document_number,
                                    inv_no = inv_num,
                                    row_data=row_data,
                                    status='pending'
                                )

                            saved_count += len(group_df)


                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})

            elif data_type.lower() == 'vendormaster':
                try:
                    mapping = VendorMastersMapping.objects.filter(company=company).first()
                    # print(mapping)
                    if not mapping:
                        return {"status": "error", "message": "No vendor mapping defined for this company."}

                    # Build dict of system_field -> excel_column_name
                    field_map = {
                        "VendorName": mapping.VendorName,
                        "VendorCode": mapping.VendorCode,
                        "GSTNo": mapping.GSTNo,
                        "LDCNo": mapping.LDCNo,
                        "LDCThreshold": mapping.LDCThreshold,
                        "LDCStartDate": mapping.LDCStartDate,
                        "LDCEndDate": mapping.LDCEndDate,
                        "LDCWTCode": mapping.LDCWTCode,
                        "BlockedYN": mapping.BlockedYN,
                        "MSMERegisteredYN": mapping.MSMERegisteredYN,
                        "MSMENumber": mapping.MSMENumber,
                    }
                    # print(field_map)
                    # print(df.columns)
                    
                    # Find missing columns in uploaded sheet
                    missing_columns = [v for v in field_map.values() if v not in df.columns]
                    if missing_columns:
                        print(missing_columns)
                        context['message'] = f"Uploaded sheet missing mapped columns: {missing_columns}"
                        

                    # Save or update data
                    for _, row in df.iterrows():
                        data = {}
                        for sys_field, excel_col in field_map.items():
                            data[sys_field] = str(row[excel_col]).strip() if excel_col in df.columns else None

                        VendorMastersData.objects.update_or_create(
                            company=company,
                            VendorCode=data["VendorCode"],
                            defaults=data
                        )

                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})
            elif data_type.lower() == 'withholdtaxmaster':
                try:
                    mapping = withholdingtaxMastersMapping.objects.filter(company=company).first()
                    # print(mapping)
                    if not mapping:
                        return {"status": "error", "message": "No vendor mapping defined for this company."}

                    # Build dict of system_field -> excel_column_name
                    field_map = {
                        "wtaxcode": mapping.wtaxcode,
                        "wtaxcoderate": mapping.wtaxcoderate,
                        "ldc": mapping.ldc,
                        "ldtrate": mapping.ldtrate,
                        
                    }
                    # print(field_map)
                    # print(df.columns)
                    
                    # Find missing columns in uploaded sheet
                    missing_columns = [v for v in field_map.values() if v not in df.columns]
                    if missing_columns:
                        print(missing_columns)
                        context['message'] = f"Uploaded sheet missing mapped columns: {missing_columns}"
                        

                    # Delete old data for the company
                    withholdingtaxMastersData.objects.filter(company=company).delete()

                    # Prepare list of model instances
                    records = []
                    for _, row in df.iterrows():
                        data = {}
                        for sys_field, excel_col in field_map.items():
                            value = str(row[excel_col]).strip() if excel_col in df.columns else None
                            data[sys_field] = value

                        # Create model instance but don't save yet
                        records.append(withholdingtaxMastersData(company=company, **data))

                    # Bulk create all at once
                    withholdingtaxMastersData.objects.bulk_create(records)

                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})


            elif data_type.lower() == 'gsttaxmaster':
                try:
                    mapping = gsttaxMastersMapping.objects.filter(company=company).first()
                    # print(mapping)
                    if not mapping:
                        return {"status": "error", "message": "No vendor mapping defined for this company."}

                    # Build dict of system_field -> excel_column_name
                    field_map = {
                        "gsttaxcode": mapping.gsttaxcode,
                        "cgstrate": mapping.cgstrate,
                        "sgstrate": mapping.sgstrate,
                        "igstrate": mapping.igstrate,
                        "bc_ic": mapping.bc_ic,
                        "fc_rc": mapping.fc_rc,
                        
                    }
                    # print(field_map)
                    # print(df.columns)
                    
                    # Find missing columns in uploaded sheet
                    missing_columns = [v for v in field_map.values() if v not in df.columns]
                    if missing_columns:
                        print(missing_columns)
                        context['message'] = f"Uploaded sheet missing mapped columns: {missing_columns}"
                        

                    # Delete old data for the company
                    gsttaxMastersData.objects.filter(company=company).delete()

                    # Prepare list of model instances
                    records = []
                    for _, row in df.iterrows():
                        data = {}
                        for sys_field, excel_col in field_map.items():
                            value = str(row[excel_col]).strip() if excel_col in df.columns else None
                            data[sys_field] = value

                        # Create model instance but don't save yet
                        records.append(gsttaxMastersData(company=company, **data))

                    # Bulk create all at once
                    gsttaxMastersData.objects.bulk_create(records)

                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})
            elif data_type.lower() == 'hsnmaster':
                try:
                    mapping = HsnMastersMapping.objects.filter(company=company).first()
                    # print(mapping)
                    if not mapping:
                        print('no mapping for hsn')
                        return {"status": "error", "message": "No vendor mapping defined for this company."}

                    # Build dict of system_field -> excel_column_name
                    field_map = {
                        "hsncode": mapping.hsncode,
                        "hsnDescription": mapping.hsnDescription,
                        "cgstrate": mapping.cgstrate,
                        "sgstrate": mapping.sgstrate,
                        "igstrate": mapping.igstrate,
                        "block_input": mapping.block_input,
                        
                    }
                    # print(field_map)
                    # print(df.columns)
                    
                    # Find missing columns in uploaded sheet
                    missing_columns = [v for v in field_map.values() if v not in df.columns]
                    if missing_columns:
                        print(missing_columns)
                        context['message'] = f"Uploaded sheet missing mapped columns: {missing_columns}"
                        

                    # Delete old data for the company
                    HsnMastersData.objects.filter(company=company).delete()

                    # Prepare list of model instances
                    records = []
                    for _, row in df.iterrows():
                        data = {}
                        for sys_field, excel_col in field_map.items():
                            value = str(row[excel_col]).strip() if excel_col in df.columns else None
                            data[sys_field] = value

                        # Create model instance but don't save yet
                        records.append(HsnMastersData(company=company, **data))

                    # Bulk create all at once
                    HsnMastersData.objects.bulk_create(records)

                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})
            elif data_type.lower() == 'sacmaster':
                try:
                    mapping = SACMastersMapping.objects.filter(company=company).first()
                    # print(mapping)
                    if not mapping:
                        return {"status": "error", "message": "No vendor mapping defined for this company."}

                    # Build dict of system_field -> excel_column_name
                    field_map = {
                        "saccode": mapping.saccode,
                        "sacDescription": mapping.sacDescription,
                        "taxrate": mapping.taxrate,
                        "block_input": mapping.block_input,
                        "rcm_fc": mapping.rcm_fc,    
                    }
                    # print(field_map)
                    # print(df.columns)
                    
                    # Find missing columns in uploaded sheet
                    missing_columns = [v for v in field_map.values() if v not in df.columns]
                    if missing_columns:
                        print(missing_columns)
                        context['message'] = f"Uploaded sheet missing mapped columns: {missing_columns}"
                        

                    # Delete old data for the company
                    SACMastersData.objects.filter(company=company).delete()

                    # Prepare list of model instances
                    records = []
                    for _, row in df.iterrows():
                        data = {}
                        for sys_field, excel_col in field_map.items():
                            value = str(row[excel_col]).strip() if excel_col in df.columns else None
                            data[sys_field] = value

                        # Create model instance but don't save yet
                        records.append(SACMastersData(company=company, **data))

                    # Bulk create all at once
                    SACMastersData.objects.bulk_create(records)

                    return JsonResponse({"status": "ok"})
                except Exception as e:
                    print("Error occurred:", e)
                    traceback.print_exc()
                    return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})
            
            else:
                return JsonResponse({"status": "ok", 'error': f"Error processing file: No headers mapping found for {data_type} file"})

        except Exception as e:
            return JsonResponse({"status": "ok", 'error': f"Error processing file: {str(e)}"})

    

def radiobuttontest(request):
    company = request.user.company_code
    invoice_data = api_response_test.get('result').get('Invoice_data')

    try:
        configurations = configuration_setting(company, api_response_test)
    except Exception as e:
        print("Error:", e)
        traceback.print_exc()

    radio_checks = radio_checkss(company, configurations, api_response_test)
    # print(radio_checks)
    for key, value in radio_checks.items():
        data_str = value.get("data", "{}")
        color = value.get("color")
        # print(data_str)
        try:
            data_str = json.loads(data_str)
        except:
            pass

        # Only modify if color is 'r' or 'o'
        if color in ("r", "o"):
            if isinstance(data_str, list):
                # Case 1: data is a list of dicts
                for item in data_str:
                    if isinstance(item, dict):
                        item.setdefault("processor_remark", "")
                        item.setdefault("checker_remark", "")
            elif isinstance(data_str, dict):
                # Case 2: data is a dict (may contain nested dicts)
                for inner_key, inner_val in data_str.items():
                    if isinstance(inner_val, dict):
                        handle_nested_dict(inner_val)
                    elif isinstance(inner_val, list):
                        for item in inner_val:
                            if isinstance(item, dict):
                                handle_nested_dict(item)

    return JsonResponse({"radio_checks": radio_checks})

def handle_nested_dict(d):
    """
    Add remark keys only if the dict has color r/o,
    and apply same rule for nested dicts/lists inside it.
    """
    if not isinstance(d, dict):
        return

    # If this dict has red/orange color → add remark keys
    if d.get("color") in ("r", "o"):
        d.setdefault("processor_remark", "")
        d.setdefault("checker_remark", "")

    # Recursively handle nested structures
    for k, v in d.items():
        if isinstance(v, dict):
            handle_nested_dict(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    handle_nested_dict(item)


def data_gathering(api_response, company, unique_name, invoice_path, invoice_key):
    print('data gathering called')
    
    invoice_data = api_response.get('result').get('Invoice_data')
    
    vendor_gst = invoice_data.get('Vendor Gst No.')
    inv_curr = invoice_data.get('Currency')
    invoice_num = invoice_data.get('InvoiceId')
    invoice_num = re.sub(r'[^A-Za-z0-9]', '', invoice_num)
    system_mapping = SystemVariableMapping.objects.filter(company_id=company)
    vendor_master_data = VendorMastersData.objects.filter(company_id=company,GSTNo=vendor_gst).first()
    vendorcode = None
    if vendor_master_data:
        vendorcode = vendor_master_data.VendorCode
    else:
        vendorcode = invoice_data.get('VendorCode')
        vendor_master_data = VendorMastersData.objects.filter(company_id=company,VendorCode=vendorcode).first()

    # print('vendorcode', vendorcode)
    migo_data = OpenGRNData.objects.filter(company_id=company,vendor_code=vendorcode,inv_no=invoice_num)
    # Build a dict of {system_var: miro_header}
    # print(list(system_mapping.values()))
    if migo_data:
        try:
            field_map = {m.system_var: m.miro_header for m in system_mapping if m.miro_header}
        except:
            pass
        doctype = DOCTYPE['invoice']
        # print('hello')
        try:
            configurations = configuration_setting(company,api_response)
        except Exception as e:
            print("Error:", e)
            traceback.print_exc()   # ✅ This prints the exact line where error occurred
        # print('hello1')
        radio_checks = radio_checkss(company,configurations,api_response)
        for key, value in radio_checks.items():
            data_str = value.get("data", "{}")
            color = value.get("color")
            # print(data_str)
            try:
                data_str = json.loads(data_str)
            except:
                pass

            # Only modify if color is 'r' or 'o'
            if color in ("r", "o"):
                if isinstance(data_str, list):
                    # Case 1: data is a list of dicts
                    for item in data_str:
                        if isinstance(item, dict):
                            item.setdefault("processor_remark", "")
                            item.setdefault("checker_remark", "")
                elif isinstance(data_str, dict):
                    # Case 2: data is a dict (may contain nested dicts)
                    for inner_key, inner_val in data_str.items():
                        if isinstance(inner_val, dict):
                            handle_nested_dict(inner_val)
                        elif isinstance(inner_val, list):
                            for item in inner_val:
                                if isinstance(item, dict):
                                    handle_nested_dict(item)

        # Re-serialize back to JSON string
        # value["data"] = json.dumps(data_str)
        for key, value in radio_checks.items():
            value['data'] = json.dumps(value.get('data', {}))
        
        # print(radio_checks)
        if invoice_data.get('Tax_Invoice') == 'Credit':
            doctype = DOCTYPE['credit']
        # print('hello2')
        mapped_data_list = []
        if vendor_master_data:
            # print('entered')
            vendorcode = vendor_master_data.VendorCode

             
            if migo_data:
                for record in migo_data:
                    row_data = record.row_data  # JSONField → usually a dict or list of dicts
                    data_dict = {}
                    for sys_field, excel_key in field_map.items():
                        value = row_data.get(excel_key, "")
                        data_dict[sys_field] = str(value).strip()

                    data_dict["VendorCode"] = record.vendor_code
                    data_dict["VendorName"] = vendor_master_data.VendorName
                    data_dict["DocumentNumber"] = record.document_number
                    data_dict["DocType"] = doctype
                    data_dict["Narration"] = configurations.get('narration')
                    data_dict["WBS_Element"] = ''
                    data_dict["UnplannedDeliveryCost"] = ''
                    data_dict["BaselineDate"] = configurations.get('BaselineDate') or ''
                    data_dict["PaymentBlock"] = configurations.get('block_pay', {}).get('action')
                    data_dict["PostingDate"] = configurations.get('posting_date')
                    # data_dict["PostingDate"] = configurations.get('WithHolding Tax Details', {}).get('WithHolding Tax value')
                    

                    # attach the same unique key
                    data_dict["invoice_key"] = invoice_key

                    # Save record
                    InvoiceDetails.objects.create(
                        company=company,
                        **data_dict
                    )
                    mapped_data_list.append(data_dict)
                Gst_taxrate = data_dict.get('TaxCode')
                Whold_taxrate = data_dict.get('WithholdingTaxCode')
                raw_date = data_dict.get("InvoiceDate")
                payment_block = data_dict.get("PaymentBlock")
                if raw_date:
                    # handle "2025-04-07 00:00:00" → "2025-04-07"
                    try:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").date()
                    except:
                        # If already "YYYY-MM-DD", just split
                        parsed_date = raw_date.split(" ")[0]
                else:
                    parsed_date = None

                print('pay block indicator--->',configurations.get('block_pay', {}).get('action'))
                # create 1 summary record (you can use another model, e.g. InvoiceSummary) 
                InvoiceSummary.objects.create(
                    company=company,
                    InvoiceGroupKey=invoice_key,
                    unique_name = unique_name,
                    path = invoice_path,
                    VendorCode=vendorcode,
                    Narration=configurations.get('narration'),
                    TaxCode=Gst_taxrate,
                    VendorGst=vendor_gst,
                    WithholdingTaxCode=Whold_taxrate,
                    VendorName=data_dict["VendorName"],  
                    InvoiceNo=data_dict["SuppInv_no"],
                    Currency=data_dict["Currency"],
                    InvCurrency = inv_curr,
                    ExchangeRate=data_dict["ExchangeRate"],
                    InvoiceDate=parsed_date,
                    InvoiceCheck = radio_checks,
                    payment_indicator = configurations.get('block_pay', {}).get('action'),
                    account_indicator = configurations.get('block_acc', {}).get('action'),
                    InvoiceValue=data_dict["InvoiceAmount"],
                    Pending_with = 'Processor',
                    Status="Pending"  # or whatever your initial state is
                )
            else:
                # create 1 summary record (you can use another model, e.g. InvoiceSummary) 
                InvNo=str(invoice_data.get('InvoiceId', '')),
                message = f"No data found against Invoice Number {InvNo} for Vendor {vendorcode} in MIGO report"
                MissingDataInvoices.objects.update_or_create(
                    company=company,
                    InvNo=str(invoice_data.get('InvoiceId', '')),
                    defaults={
                        "VendorGst": invoice_data.get('Vendor Gst No.', ''),
                        "InvDate": invoice_data.get('InvoiceDate', ''),
                        "VendorName": invoice_data.get('VendorAddressRecipient') or invoice_data.get('VendorName'),
                        "VendorCode": vendorcode,
                        "CustomerGst": invoice_data.get('Cutomer Gst No.', ''),
                        "TotalAmount": str(invoice_data.get('InvoiceTotal', '')),
                        "TotalTax": str(invoice_data.get('TotalTax', '')),
                        "BasicAmount": str(invoice_data.get('SubTotal', '')),
                        "TaxType": invoice_data.get('Tax Items', {}),  # ✅ use dict, not str()
                        "path": invoice_path,                          # ✅ corrected field name
                        "unique_name": unique_name,                     # ✅ corrected field name
                        "message": message,
                        "api_response": api_response
                    }
                )
                
                
        
        else:
            print(f'No VendorCode in masters for this Gst Number {vendor_gst}')
    else:
        pass
    
    
    

def invoices(request):
    company = request.user.company_code
    role = request.user.role
    role_matrix = RoleMatrix.objects.filter(company_id=company).first()
    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    unique_data_list = InvoiceSummary.objects.filter(company_id=company, Pending_with="Processor", Status='Pending')

    # ✅ Only serialize rolematrix if needed for JS
    rolematrix_json = json.dumps(rolematrix)
    print(rolematrix_json)
    return render(
        request,
        'submitted_invoices.html',
        {
            'company': company,
            'data': unique_data_list,         # use directly in HTML loop
            'rolematrix': rolematrix_json,    # safe for JS
            'role': role,
        }
    )

def checker_dashboard(request):
    company = request.user.company_code

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()
    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    unique_data_list = InvoiceSummary.objects.filter(company_id=company, Pending_with="Checker", Status='Pending')

    # ✅ Only serialize rolematrix if needed for JS
    rolematrix_json = json.dumps(rolematrix)

    return render(
        request,
        'checker_dashboard.html',
        {
            'company': company,
            'data': unique_data_list,         # use directly in HTML loop
            'rolematrix': rolematrix_json,    # safe for JS
        }
    )

def nodata_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = PendingInvoices.objects.filter(
        company=company
    ).values()                       # ✅ convert to JSON-friendly dicts
    # print(list(unique_data_list))
    return JsonResponse({
        # 'company': company,
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def waiting_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = MissingDataInvoices.objects.filter(
        company_id=company
    ).values()                       # ✅ convert to JSON-friendly dicts
    print(unique_data_list)
    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def hold_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = InvoiceSummary.objects.filter(
        company_id=company,
        Status='hold'
    ).values()                       # ✅ convert to JSON-friendly dicts

    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def rejected_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = InvoiceSummary.objects.filter(
        company_id=company,
        Status='rejected'
    ).values()                       # ✅ convert to JSON-friendly dicts

    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def ready_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = InvoiceSummary.objects.filter(
        company_id=company,
        Status='ready'
    ).values()                       # ✅ convert to JSON-friendly dicts

    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def pendingwithchecker(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = InvoiceSummary.objects.filter(
        company_id=company,
        Status='Pending',
        Pending_with = 'Checker'
    ).values()                       # ✅ convert to JSON-friendly dicts

    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

def generated_invoices(request):
    company = request.user.company_code

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    role_matrix = RoleMatrix.objects.filter(company_id=company).first()

    rolematrix = {
        'field_matrix': role_matrix.field_matrix if role_matrix else {},
        'radio_matrix': role_matrix.radio_matrix if role_matrix else {},
    }

    # Correct filter — No Data only
    unique_data_list = InvoiceSummary.objects.filter(
        company_id=company,
        Status='generated'
    ).values()                       # ✅ convert to JSON-friendly dicts

    return JsonResponse({
        
        "data": list(unique_data_list),   # ✅ serializable
        "rolematrix": rolematrix,
    }, safe=False)

from datetime import datetime
from dateutil.parser import parse

def normalize_date(date_str):
    """Try multiple formats and return a date object if any match."""
    possible_dates = []

    # Format 1: DD-MM-YYYY
    try:
        d = datetime.strptime(date_str, "%d-%m-%Y").date()
        possible_dates.append(d)
    except:
        pass

    # Format 2: MM-DD-YYYY
    try:
        d = datetime.strptime(date_str, "%m-%d-%Y").date()
        possible_dates.append(d)
    except:
        pass

    # Format 3: Auto detect (with dayfirst=True)
    try:
        d = parse(date_str, dayfirst=True).date()
        possible_dates.append(d)
    except:
        pass

    # Unique results only
    return list(set(possible_dates))   # remove duplicates


def radio_checkss(company,configurations,api_response_):

    invoice_data = api_response_.get('result').get('Invoice_data')
    tax_check = api_response_.get('result').get('CHECKS').get('tax_check')
    complete_invoice = api_response_.get('result').get('CHECKS').get('Account_check')
    vendor_gst = invoice_data.get('Vendor Gst No.')
    invoice_num = invoice_data.get('InvoiceId')
    # print(invoice_num)
    invoice_num = re.sub(r'[^A-Za-z0-9]', '', invoice_num)
    system_mapping = SystemVariableMapping.objects.filter(company_id=company)
    vendor_master_data = VendorMastersData.objects.filter(company_id=company,GSTNo=vendor_gst).first()
    vendorcode = vendor_master_data.VendorCode
    migo_data = OpenGRNData.objects.filter(company_id=company,vendor_code=vendorcode,inv_no=invoice_num)
    # inv_item_level_data = InvoiceDetails.objects.filter(company_id=company,VendorCode=vendorcode,SuppInv_no=invoice_num)
    # if inv_item_level_data:
    #     print('yes data found for inv number in invoiedetails')
    # Build a dict of {system_var: miro_header}
    field_map = {m.system_var: m.miro_header for m in system_mapping if m.miro_header}

    invoice_table = invoice_data.get('Invoice items:',{})
    hsn_list = []
    for key,value in invoice_table.items():
        if 'product_code' in value:
            hsn_list.append(value.get('product_code'))

    radio_checks = {}

    #### 1.matching check ---> radio button1
    invoice_calulation_matching_check = {}
    matching = {}
    invoice_calulation_matching_check["data"] = {}
    data_r1 = {}
    invoice_calulation1 = {}
    invoice_calulation2 = {}
    otherchecks = {}
    color_r1 = 'g'
    basic_amount_check = {}
    total_amount_check = {}
    try:
        # print('configuration--> ',configurations)
        table_df = configurations['2/3_Way_Matching'].get('table')
        table_df['status'] = table_df['status'].astype(str).str.capitalize()
        table_df.rename(columns=lambda c: c.replace("grn", "GRN").replace("Grn", "GRN").replace("GRn", "GRN"), inplace=True)
        # print(table_df.columns)
        try:
            if configurations['2/3_Way_Matching'].get('result') == 'Okay':
                matching['color'] = 'g'
            else:
                matching['color'] = 'r'
                color_r1 = 'r'
            matching['message'] = '2/3 way match result'
            # Convert DataFrame to list of dicts safely
            if isinstance(table_df, pd.DataFrame):
                matching['data'] = table_df.to_dict(orient='records')
            else:
                matching['data'] = []
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        try:
            inv_table = invoice_data.get('Invoice items:', {})

            # Convert dict → list → DataFrame
            rows = [v for v in inv_table.values()]      # safer than .items()
            df = pd.DataFrame(rows)

            # Ensure df is not empty and has 'amount'
            if not df.empty and 'amount' in df.columns:
                df['amount'] = df['amount'].astype(float)  # convert strings → float
                table_sum_amount = df['amount'].sum()
                inv_basic_amt = float(invoice_data.get('SubTotal'))
                inv_total_amt = float(invoice_data.get('InvoiceTotal'))
                inv_tax_amt = float(invoice_data.get('TotalTax'))
                try:
                    if abs(table_sum_amount-inv_basic_amt) < 2:
                        invoice_calulation1['ocr_captured_amount'] = inv_basic_amt
                        invoice_calulation1['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation1['color'] = 'g'
                        invoice_calulation1['status'] = 'Matched'
                    elif abs(table_sum_amount-inv_total_amt) < 2:
                        invoice_calulation1['ocr_captured_amount'] = inv_total_amt
                        invoice_calulation1['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation1['status'] = 'Matched'
                        invoice_calulation1['color'] = 'g'
                    else:
                        invoice_calulation1['ocr_captured_amount'] = inv_total_amt
                        invoice_calulation1['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation1['color'] = 'r'
                        invoice_calulation1['status'] = 'Not Matched'
                        color_r1 = 'r'
                except Exception as e:
                    print(f"Error {e}")
                    traceback.print_exc()
                
                try:
                    if abs((table_sum_amount+inv_tax_amt)-inv_total_amt) < 2:
                        invoice_calulation2['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation2['ocr_captured_tax'] = inv_tax_amt
                        invoice_calulation2['ocr_captured_total_amount'] = inv_total_amt
                        invoice_calulation2['status'] = 'Matched'
                        invoice_calulation2['color'] = 'g'

                    if abs((table_sum_amount-inv_tax_amt)-inv_basic_amt) < 2:
                        invoice_calulation2['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation2['ocr_captured_tax'] = inv_tax_amt
                        invoice_calulation2['ocr_captured_total_amount'] = inv_basic_amt
                        invoice_calulation2['status'] = 'Matched'
                        invoice_calulation2['color'] = 'g'
                    
                    else:
                        invoice_calulation2['table_sum_of_item_level'] = table_sum_amount
                        invoice_calulation2['ocr_captured_tax'] = inv_tax_amt
                        invoice_calulation2['ocr_captured_total_amount'] = inv_total_amt
                        invoice_calulation2['status'] = ' Not Matched'
                        invoice_calulation2['color'] = 'r'
                        color_r1 = 'r'
                except Exception as e:
                    print(f"Error {e}")
                    traceback.print_exc()


            else:
                invoice_calulation1['ocr_captured_amount'] = inv_total_amt
                invoice_calulation1['table_sum_of_item_level'] = 'No table captured by ocr or Amount column is missing'
                invoice_calulation1['color'] = 'r'
                invoice_calulation1['status'] = 'Not Matched'

                invoice_calulation2['table_sum_of_item_level'] = 'No table captured by ocr or Amount column is missing'
                invoice_calulation2['ocr_captured_tax'] = inv_tax_amt
                invoice_calulation2['ocr_captured_total_amount'] = inv_total_amt
                invoice_calulation2['color'] = 'r'
                invoice_calulation2['status'] = 'Not Matched'
                color_r1 = 'r'
            
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        try:
            date_check = {}
            exchange_rate = {}
            payment_check = {}
            try:
                inv_date_str = invoice_data.get("InvoiceDate")  # always YYYY-MM-DD
                inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()

                migo_raw = migo_data[0].row_data.get(field_map['InvoiceDate'])

                # Get all possible interpretations
                migo_date_candidates = normalize_date(migo_raw)

                matched = False

                for d in migo_date_candidates:
                    if d == inv_date:
                        matched = True
                        break
                date_check['Invoice/OCR'] = inv_date_str
                date_check['Migo'] = migo_raw
                
                if matched:
                    date_check['color'] = 'g'
                    date_check['Difference'] = 'No'
                else:
                    date_check['color'] = 'r'
                    date_check['Difference'] = 'Yes'
                    color_r1 = 'r'    
                # print("MIGO Date (converted):", matched_date.strftime("%Y-%m-%d"))
                
            except Exception as e:
                print(f"Error {e}")
                traceback.print_exc()

            try:
                current_exchange_rate = configurations.get('exchange_rate')
                tolerance = configurations.get('exchange_rate')
                if 'ExchangeRate' in field_map:
                    exchange_rate_migo = migo_data[0].row_data.get(field_map['ExchangeRate'])                
                    def diff_(a,b):
                        diff = abs(a-b)
                        diff_percent = (diff/b)*100
                        return diff_percent
                    
                    if current_exchange_rate not in (None, 0, "0", "", "0.0") \
                    and exchange_rate_migo not in (None, 0, "0", "", "0.0"):
                        diff = diff_(float(current_exchange_rate), float(exchange_rate_migo))
                        if float(tolerance) > diff:
                            exchange_rate['Invoice/OCR'] = current_exchange_rate
                            exchange_rate['Migo'] = exchange_rate_migo
                            exchange_rate['Difference'] = diff
                            exchange_rate['color'] = 'g'
                    else:
                        exchange_rate['Invoice/OCR'] = current_exchange_rate
                        exchange_rate['Migo'] = exchange_rate_migo
                        exchange_rate['Difference'] = 'Migo Exchange Rate Missing or 0'
                        exchange_rate['color'] = 'r'
                        color_r1 = 'r'
                else:
                    exchange_rate['Invoice/OCR'] = current_exchange_rate
                    exchange_rate['Migo'] = 'Excahnge Rate Column is not mapped with Migo Data Column'
                    exchange_rate['Difference'] = 'Migo Exchange Rate Missing or 0or Column is not mapped'
                    exchange_rate['color'] = 'r'  
                    color_r1 = 'r'             
                # print("MIGO Date (converted):", matched_date.strftime("%Y-%m-%d"))
                
            except Exception as e:
                print(f"Error {e}")
                traceback.print_exc()
            otherchecks['inv_date'] = date_check
            otherchecks['exchange_rate'] = exchange_rate
            otherchecks['payment_check'] = payment_check

        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()
    basic_amount_check['basic_amount'] = invoice_calulation1
    total_amount_check['total_amount'] = invoice_calulation2
    data_r1['2/3 Way Match'] = matching
    data_r1['Invoice Calculation1'] = basic_amount_check
    data_r1['Invoice Calculation2'] = total_amount_check
    data_r1['Other Checks'] = otherchecks
    invoice_calulation_matching_check['data'] = data_r1
    invoice_calulation_matching_check['color'] = color_r1
    invoice_calulation_matching_check['message'] = '2/3 Way Match + Invoice Calculation Check'
    # print('invoice_calulation_matching_check', invoice_calulation_matching_check)


    ### 2. complete invoice---> radio button2 
    complete_invoice_ = {}
    parameters_check = {}
    name_address_check = {}
    color_r2 = 'g'
    # print(complete_invoice)
    try:
        
        try:
            name = complete_invoice.get('Customer_Name',{})
            name['color'] = 'r'
            address = complete_invoice.get('Customer_Adress',{})
            address['color'] = 'r'
            
            if name.get('status') == 'matching':
                name['color'] = 'g'
            if address.get('status') == 'matching':
                address['color'] = 'g'
            else:
                color_r2 = 'r'
            name_address_check['name'] = name
            name_address_check['address'] = address
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        invoice_date = {}
        invoice_no = {}
        previous_year = {}
        gst_no_gstcharged = {}
        valid_invoice = {}
        try:
            invoice_date['status'] = 'Okay'
            invoice_date['color'] = 'g'
            invoice_date['data'] = complete_invoice.get('Invoice_Date',{}).get('Invoice_data')
            if complete_invoice.get('Invoice_Date',{}).get('status') != 'Okay':   # 'Okay'
                color_r2 = 'r'
                invoice_date['status'] = 'Not Okay'
                invoice_date['color'] = 'r'
                
                
            invoice_no['status'] = 'Okay'
            invoice_no['color'] = 'g'
            invoice_no['data'] = complete_invoice.get('Invoice_Number',{}).get('Invoice_data')
            if complete_invoice.get('Invoice_Number',{}).get('status') != 'Okay':   # 'Okay'
                color_r2 = 'r'
                invoice_no['status'] = 'Not Okay'
                invoice_no['color'] = 'r'

            previous_year['status'] = 'No'
            previous_year['color'] = 'g'
            previous_year['data'] = complete_invoice.get('Pre_year',{}).get('Invoice_data')
            if complete_invoice.get('Pre_year',{}).get('status') != 'NO':   # 'Okay'
                color_r2 = 'r'
                previous_year['status'] = 'Yes'
                previous_year['color'] = 'r'

            gst_no_gstcharged['status'] = 'Okay'
            gst_no_gstcharged['color'] = 'g'
            gst_no_gstcharged['data'] = invoice_data.get('Vendor Gst No.')
            if complete_invoice.get('gstnumber_gstcharged',{}).get('status') != 'Okay':   # 'Okay'
                color_r2 = 'r'
                gst_no_gstcharged['status'] = 'Not Okay'
                gst_no_gstcharged['color'] = 'r'

            valid_invoice['status'] = 'Yes'
            valid_invoice['color'] = 'g'
            valid_invoice['data'] = 'Invoice is Checked if it falls under [PI,Estimate,Commercial,Supply invoice,Challan]'
            if complete_invoice.get('valid_invoice',{}).get('status') != 'YES':   # 'Okay'
                color_r2 = 'r'
                valid_invoice['status'] = 'No'
                valid_invoice['color'] = 'r'
    
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        parameters_check['invoice_date'] = invoice_date
        parameters_check['invoice_no.'] = invoice_no
        parameters_check['previous_year'] = previous_year
        parameters_check['gst_no_mentioned?_(Only if gst is charged)'] = gst_no_gstcharged
        parameters_check['valid_invoice'] = valid_invoice
        
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()

    data_r2 = {}
    data_r2['Name & Address Check'] = name_address_check
    data_r2['Other Parameter Check'] = parameters_check
    
    complete_invoice_['message'] = 'Complete Invoice Check'
    complete_invoice_['data'] = data_r2
    complete_invoice_['color'] = color_r2


    ### 3. duplicate check----> radio button3
    duplicate_check = {}
    duplicate_check['color'] = 'g'
    duplicate_check['data'] = {}
    duplicate_check['message'] = 'Duplicate Invoice Check'


    ### valid vendor check----> radio button4
    valid_vendor = {}
    filing_status_data = api_response_.get('result',{}).get('CHECKS',{}).get('data_from_gst',{}).get("Filing Status")
    data_r4 = {}
    color_r4 = 'g'
    data_r4['GST No. of Vendor Valid as per GSTN'] = {}
    data_r4['GST No. of Vendor active on GSTN'] = {}
    data_r4['Vendor Tax Payer Type'] = {}
    data_r4['Vendor Tax Payer- Filing Frequency'] = {}
    data_r4['Vendor GSTR 3B Filing Status'] = {}
    data_r4['Previous Period (Period1) GSTR 3B'] = {}
    data_r4['Period Prior To Period1 (Period2) GSTR 3B'] = {}
    data_r4['Period Prior To Period2 (Period3) GSTR 3B'] = {}
    data_r4['Vendor GSTR 1 Filing Status'] = {}
    data_r4['Previous Period (Period1) GSTR 1'] = {}
    data_r4['Period Prior To Period1 (Period2) GSTR 1'] = {}
    data_r4['Period Prior To Period2 (Period3) GSTR 1'] = {}

    try:
        data_r4['GST No. of Vendor Valid as per GSTN']['Status/Value'] = 'Yes'
        data_r4['GST No. of Vendor Valid as per GSTN']['color'] = 'g'
        if tax_check.get('Vendor_Gst_Valid',{}).get('status') != 'YES':
            data_r4['GST No. of Vendor Valid as per GSTN']['Status/Value'] = 'No'
            data_r4['GST No. of Vendor Valid as per GSTN']['color'] = 'r'
            color_r4 = 'r'
        data_r4['GST No. of Vendor active on GSTN']['Status/Value'] = 'Yes'
        data_r4['GST No. of Vendor active on GSTN']['color'] = 'g'
        if tax_check.get('Vendor_Gst_Active',{}).get('status') != 'YES':
            data_r4['GST No. of Vendor active on GSTN']['Status/Value'] = 'No'
            data_r4['GST No. of Vendor active on GSTN']['color'] = 'r'
            color_r4 = 'r'
        data_r4['Vendor Tax Payer Type']['Status/Value'] = 'Not Regular'
        data_r4['Vendor Tax Payer Type']['color'] = 'r'
        if tax_check.get('Vendor_TaxPayer_type',{}).get('status') == 'Regular':
            data_r4['Vendor Tax Payer Type']['Status/Value'] = 'Regular'
            data_r4['Vendor Tax Payer Type']['color'] = 'g'
        data_r4['Vendor Tax Payer- Filing Frequency']['Status/Value'] = 'Monthly'
        data_r4['Vendor Tax Payer- Filing Frequency']['color'] = 'g'
        if tax_check.get('Vendor_Taxfiliging_Frequency',{}).get('status') != 'Monthly':
            data_r4['Vendor Tax Payer- Filing Frequency']['Status/Value'] = 'Quaterly'
            data_r4['Vendor Tax Payer- Filing Frequency']['color'] = 'g'

        
        
        try:
            result_gstr3,result_gstr1,df1,df2 = filingstatus(filing_status_data)
            try:
                data_r4['Vendor GSTR 3B Filing Status'] = ''
                if result_gstr3:
                    data_r4['Previous Period (Period1) GSTR 3B']['Status/Value'] = result_gstr3['month']
                    data_r4['Period Prior To Period1 (Period2) GSTR 3B']['Status/Value'] = result_gstr3['month1']
                    data_r4['Period Prior To Period2 (Period3) GSTR 3B']['Status/Value'] = result_gstr3['month2']
                    if result_gstr3['status'] != 'Filed':
                        data_r4['Previous Period (Period1) GSTR 3B']['color'] = 'r'
                        data_r4['Period Prior To Period1 (Period2) GSTR 3B']['color'] = 'r'
                        data_r4['Period Prior To Period2 (Period3) GSTR 3B']['color'] = 'r'
                        color_r4 = 'r'
                    else:
                        data_r4['Previous Period (Period1) GSTR 3B']['color'] = 'g'
                        data_r4['Period Prior To Period1 (Period2) GSTR 3B']['color'] = 'g'
                        data_r4['Period Prior To Period2 (Period3) GSTR 3B']['color'] = 'g'
                else:  ###only for now
                    data_r4['Previous Period (Period1) GSTR 3B'] = 'Not Filed'
                    data_r4['Period Prior To Period1 (Period2) GSTR 3B'] = 'Filed'
                    data_r4['Period Prior To Period2 (Period3) GSTR 3B'] = 'Filed'
                    data_r4['Previous Period (Period1) GSTR 3B']['color'] = 'r'
                    data_r4['Period Prior To Period1 (Period2) GSTR 3B']['color'] = 'r'
                    data_r4['Period Prior To Period2 (Period3) GSTR 3B']['color'] = 'r'
                    color_r4 = 'r'
            except Exception as e:
                print(f"Error {e}")
                traceback.print_exc()
        
            
            try:
                data_r4['Vendor GSTR 1 Filing Status'] = ''           
                if result_gstr1:
                    data_r4['Previous Period (Period1) GSTR 1']['Status/Value'] = result_gstr1['month']
                    data_r4['Period Prior To Period1 (Period2) GSTR 1']['Status/Value'] = result_gstr1['month1']
                    data_r4['Period Prior To Period2 (Period3) GSTR 1']['Status/Value'] = result_gstr1['month2']
                    if result_gstr1['status'] != 'Filed':
                        data_r4['Previous Period (Period1) GSTR 1']['color'] = 'r'
                        data_r4['Period Prior To Period1 (Period2) GSTR 1']['color'] = 'r'
                        data_r4['Period Prior To Period2 (Period3) GSTR 1']['color'] = 'r'
                    else:
                        data_r4['Previous Period (Period1) GSTR 1']['color'] = 'g'
                        data_r4['Period Prior To Period1 (Period2) GSTR 1']['color'] = 'g'
                        data_r4['Period Prior To Period2 (Period3) GSTR 1']['color'] = 'g'
                else:
                    data_r4['Previous Period (Period1) GSTR 1']['Status/Value'] = 'No data Recieved from GST Portal'
                    data_r4['Period Prior To Period1 (Period2) GSTR 1']['Status/Value'] = 'No data Recieved from GST Portal'
                    data_r4['Period Prior To Period2 (Period3) GSTR 1']['Status/Value'] = 'No data Recieved from GST Portal'
                    data_r4['Previous Period (Period1) GSTR 1']['color'] = 'r'
                    data_r4['Period Prior To Period1 (Period2) GSTR 1']['color'] = 'r'
                    data_r4['Period Prior To Period2 (Period3) GSTR 1']['color'] = 'r'
                    if result_gstr1['status'] != 'Filed':
                        color_r4 = 'r'
            except Exception as e:
                print(f"Error {e}")
                traceback.print_exc()
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
            print('entering into except block')
            # SAFE fallback values
            
            data_r4['Vendor GSTR 3B Filing Status']['Status/Value'] = ''
            data_r4['Vendor GSTR 3B Filing Status']['color'] = 'g'
            data_r4['Previous Period (Period1) GSTR 3B']['Status/Value']  = 'Not Filed'
            data_r4['Period Prior To Period1 (Period2) GSTR 3B']['Status/Value']  = 'Filed'
            data_r4['Period Prior To Period2 (Period3) GSTR 3B']['Status/Value']  = 'Filed'
            data_r4['Previous Period (Period1) GSTR 3B']['color'] = 'r'
            data_r4['Period Prior To Period1 (Period2) GSTR 3B']['color'] = 'r'
            data_r4['Period Prior To Period2 (Period3) GSTR 3B']['color'] = 'r'
            color_r4 = 'r'
            
            data_r4['Vendor GSTR 1 Filing Status']['Status/Value'] = ''
            data_r4['Vendor GSTR 1 Filing Status']['color'] = 'g'
            data_r4['Previous Period (Period1) GSTR 1']['Status/Value'] = 'Filed'
            data_r4['Period Prior To Period1 (Period2) GSTR 1']['Status/Value'] = 'Filed'
            data_r4['Period Prior To Period2 (Period3) GSTR 1']['Status/Value'] = 'Filed'
            data_r4['Previous Period (Period1) GSTR 1']['color'] = 'g'
            data_r4['Period Prior To Period1 (Period2) GSTR 1']['color'] = 'g'
            data_r4['Period Prior To Period2 (Period3) GSTR 1']['color'] = 'g'
            
            
            
    
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()
        
    print(data_r4)  
        
    valid_vendor['color'] = color_r4
    valid_vendor['data'] = data_r4
    valid_vendor['message'] = "Valid Vendor Check"
    


    #### gst tax check----> radiobutton5
    gsttax_check = {}
    gsttax_check_data = {}
    gsttax_check['data'] = {}
    
    try:
        print('entering into gst check')
        migo_invoice_taxrate = {}
        migo_invoice_taxtype = {}
        migo_invoice_bc_check = {}
        migo_invoice_rcm_check = {}
        eway_bill_check = {}
        data_r5 = {}
        migo_taxcode = migo_data[0].row_data.get(field_map['TaxCode'])
        ### Eway bill data
        try:
            vendor_gst_eway = {}
            invoice_number_eway = {}
            total_amount_eway = {}
            ewaybill_response = api_response_.get('result',{}).get('CHECKS').get('eway_bill_data')
            print(ewaybill_response)
            invoice_number_eway = ewaybill_response.get('Invoice_No')
            invoice_number_eway['color'] = 'g'
            if invoice_number_eway['invoice'] != invoice_number_eway['e-waybill']:
                invoice_number_eway['color'] = 'r'
            vendor_gst_eway = ewaybill_response.get('Vendor_Gst')
            vendor_gst_eway['color'] = 'g'
            if vendor_gst_eway['invoice'] != vendor_gst_eway['e-waybill']:
                vendor_gst_eway['color'] = 'r'
            total_amount_eway = ewaybill_response.get('Total_Amount')
            total_amount_eway['color'] = 'g'
            if total_amount_eway['invoice'] != total_amount_eway['e-waybill']:
                total_amount_eway['color'] = 'r'
            
            
            eway_bill_check['vendor_gst'] = vendor_gst_eway
            eway_bill_check['invoice_number'] = invoice_number_eway
            eway_bill_check['total_amount'] = total_amount_eway
            
            
            
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        if migo_taxcode:
            # print('tax code found in migo data', migo_taxcode)
            master_taxcode = gsttaxMastersData.objects.filter(company_id=company,gsttaxcode=migo_taxcode).first()
            if master_taxcode:
                try:
                    print("entering into tax rate check")
                    # print(master_taxcode.cgstrate,master_taxcode.sgstrate)
                    # print("IGST ACTUAL VALUE:", repr(master_taxcode.igstrate), type(master_taxcode.igstrate))
                    if master_taxcode.igstrate == '0':
                        master_taxrate = int(2*float(master_taxcode.cgstrate)) or int(2*float(master_taxcode.sgstrate))
                        # print(master_taxrate)
                        master_taxtype = 'CGST & SGST'
                    else:
                        master_taxrate = int(float(master_taxcode.igstrate))
                        master_taxtype = 'IGST'
                        
                    invoice_taxitems = invoice_data.get('Tax Items')
                    SubTotal = invoice_data.get('SubTotal')
                    InvoiceTotal = invoice_data.get('InvoiceTotal')
                    TotalTax = invoice_data.get('TotalTax')
                    if invoice_taxitems.get('IGST',{}).get('rate') and invoice_taxitems.get('IGST',{}).get('rate') != 0:
                        invoice_taxrate = invoice_taxitems.get('IGST',{}).get('rate')
                        
                    elif invoice_taxitems.get('SGST',{}).get('rate') and invoice_taxitems.get('SGST',{}).get('rate') != 0:
                        invoice_taxrate = 2*invoice_taxitems.get('SGST',{}).get('rate')
                        
                    elif invoice_taxitems.get('CGST',{}).get('rate') and invoice_taxitems.get('CGST',{}).get('rate') != 0:
                        invoice_taxrate = 2*invoice_taxitems.get('CGST',{}).get('rate')
                        
                    else:
                        if SubTotal and TotalTax:
                            invoice_taxrate = int((float(TotalTax) / float(SubTotal))*100)
                            
                        else:
                            invoice_taxrate = -1
                        

                    if invoice_taxitems.get('IGST',{}).get('amount') and invoice_taxitems.get('IGST',{}).get('amount') != 0:
                        invoice_taxtype = 'IGST'
                    elif invoice_taxitems.get('SGST',{}).get('amount') and invoice_taxitems.get('SGST',{}).get('amount') != 0:
                        invoice_taxtype = 'CGST & SGST'
                    elif invoice_taxitems.get('CGST',{}).get('amount') and invoice_taxitems.get('CGST',{}).get('amount') != 0:
                        invoice_taxtype = 'CGST & SGST'
                    else:
                        invoice_taxtype = 'not captured by ocr'

                    migo_invoice_taxrate['Invoice_Data'] = invoice_taxrate
                    migo_invoice_taxrate['Master_Data'] = master_taxrate
                    migo_invoice_taxrate['color'] = 'r'
                    if int(master_taxrate) == int(invoice_taxrate):
                        migo_invoice_taxrate['color'] = 'g'

                    migo_invoice_taxtype['Invoice_Data'] = master_taxtype
                    migo_invoice_taxtype['Master_Data'] = invoice_taxtype
                    migo_invoice_taxtype['color'] = 'r'

                    if str(master_taxtype) == str(invoice_taxtype):
                        migo_invoice_taxtype['color'] = 'g'
                except Exception as e:
                    print(f"Error {e}")
                    traceback.print_exc()

                ### IC/FC check
                try:
    
                    inv_type_asper_master = 'IC'
                    if master_taxcode.bc_ic == 'BC':
                        inv_type_asper_master = 'BC'
                    inv_type_asper_invoice = 'IC'
                    try:
                        
                        # print(set(hsn_list))
                        # Query HSN Master table
                        records = HsnMastersData.objects.filter(
                            company_id=company,
                            hsncode__in=set(hsn_list),
                            block_input='BC'
                        )

                        # Check if any record exists
                        if records.exists():
                            inv_type_asper_invoice = 'BC'
                    except Exception as e:
                        print(f"Error {e}")
                        traceback.print_exc()
                    migo_invoice_bc_check['Invoice_Data'] = inv_type_asper_master
                    migo_invoice_bc_check['Master_Data'] = inv_type_asper_invoice
                    migo_invoice_bc_check['color'] = 'r'
                    if inv_type_asper_master == inv_type_asper_invoice:
                        migo_invoice_bc_check['color'] = 'g'
                except Exception as e:
                    print(f"Error {e}")
                    traceback.print_exc()
                ### RCM/FC check
                try:
    
                    inv_category_asper_master = 'FC'
                    
                    if master_taxcode.fc_rc == 'RCM':
                        inv_category_asper_master = 'RCM'
                    inv_category_asper_invoice = 'FC'
                    try:
                        
                        # Query HSN Master table
                        records = SACMastersData.objects.filter(
                            company_id=company,
                            saccode__in=set(hsn_list),
                            rcm_fc='RCM'
                        )

                        # Check if any record exists
                        if records.exists():
                            inv_category_asper_invoice = 'RCM'
                    except Exception as e:
                        print(f"Error {e}")
                        traceback.print_exc()
                    migo_invoice_rcm_check['Invoice_Data'] = inv_category_asper_master
                    migo_invoice_rcm_check['Master_Data'] = inv_category_asper_invoice
                    migo_invoice_rcm_check['color'] = 'r'
                    if inv_category_asper_master == inv_category_asper_invoice:
                        migo_invoice_rcm_check['color'] = 'g'
                except Exception as e:
                    print(f"Error {e}")
                    traceback.print_exc()

                

                
                
                gsttax_check_data['tax_rate'] = migo_invoice_taxrate
                gsttax_check_data['tax_type'] = migo_invoice_taxtype
                gsttax_check_data['Block Credit / Input Credit'] = migo_invoice_bc_check
                gsttax_check_data['RCM / Forward_Charge'] = migo_invoice_rcm_check
                
                count_gst = 4
                for key, value in gsttax_check_data.items():
                    if value['color'] == 'r':
                        count_gst = count_gst-1
                if count_gst == 4:
                    gsttax_check['color'] = 'g'
                elif count_gst == 3:
                    gsttax_check['color'] = 'o'
                else:
                    gsttax_check['color'] = 'r' 
                  
                
                data_r5['Tax Check'] = gsttax_check_data
                data_r5['Eway Bill Check'] = eway_bill_check
                gsttax_check['data'] = data_r5
                gsttax_check['message'] = 'GST Check'           
            
            
            else:
                data_r5['Tax Check'] = {'status': 'Check Skip'}
                data_r5['Eway Bill Check'] = eway_bill_check
                gsttax_check['color'] = 'r'
                gsttax_check['message'] = f'No Record found for Tax code {migo_taxcode} in master data'
                gsttax_check['data'] = data_r5
        else:
            data_r5['Tax Check'] = {'status': 'Check Skip'}
            data_r5['Eway Bill Check'] = eway_bill_check
            gsttax_check['color'] = 'r'
            gsttax_check['message'] = 'No Tax code found in MIgo data'
            gsttax_check['data'] = data_r5

                
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()
    


    #### withold tax check---> radio button6
    withholdtax_check = {}
    count = 4
    withholdtax_code = {}
    adhar_pan_link = {}
    vendor_pan = {}
    _206Ab = {}
    color_6 = 'g'
    whold_tax_section_inv = ''
    whold_tax_rate_inv = ''
    try:
        try:

            # print('tax_check--->',tax_check) 
            master_wcode = migo_data[0].row_data.get(field_map['WithholdingTaxCode'])
            whold_tax_rate_master_data = withholdingtaxMastersData.objects.filter(company_id=company,wtaxcode=master_wcode).first()#
            if whold_tax_rate_master_data:
                whold_tax_rate_master = whold_tax_rate_master_data.wtaxcoderate
                whold_tax_section_master = whold_tax_rate_master_data.wtaxsection
                if hsn_list:
                    for hsn in set(hsn_list):
                        if len(hsn) == 6 and int(hsn[:2]) == 99:
                            sac_master_data = SACMastersData.objects.filter(company_id=company,saccode=hsn).first()
                            if sac_master_data:
                                whold_tax_section_inv = sac_master_data.section
                                whold_tax_rate_master_data_inv = withholdingtaxMastersData.objects.filter(company_id=company,wtaxsection=whold_tax_section_inv).first()
                                whold_tax_rate_inv = whold_tax_rate_master_data_inv.wtaxcoderate
                                break
                            else:
                                whold_tax_section_inv = 'Data not Found in HSN/SAC Master for HSN'
                                whold_tax_rate_inv = 'Data not Found in HSN/SAC Master for HSN'
                        elif len(hsn) < 6:
                            whold_tax_section_inv = 'HSN is less than 4 Char or not captured by OCR'
                            whold_tax_rate_inv = 'HSN is less than 4 Char or not captured by OCR'
                        else:
                            whold_tax_section_inv = '194Q'
                            whold_tax_rate_master_data_inv = withholdingtaxMastersData.objects.filter(company_id=company,wtaxsection='194Q').first()
                            whold_tax_rate_inv = whold_tax_rate_master_data_inv.wtaxcoderate
                else:
                    whold_tax_section_inv = 'HSN is not captured by OCR'
                    whold_tax_rate_inv = 'HSN is not captured by OCR'  
            else:
                whold_tax_rate_master = 'WithHolding Tax Code found in Migo does not match any record in with hold tax masters'
                whold_tax_section_master = 'WithHolding Tax Code found in Migo does not match any record in with hold tax masters' 
                if hsn_list:
                    for hsn in set(hsn_list):
                        if len(hsn) == 6 and int(hsn[:2]) == 99:
                            sac_master_data = SACMastersData.objects.filter(company_id=company,saccode=hsn).first()
                            if sac_master_data:
                                whold_tax_section_inv = sac_master_data.section
                                whold_tax_rate_master_data_inv = withholdingtaxMastersData.objects.filter(company_id=company,wtaxsection=whold_tax_section_inv).first()
                                whold_tax_rate_inv = whold_tax_rate_master_data_inv.wtaxcoderate
                                break
                        elif len(hsn) < 6:
                            whold_tax_section_inv = 'HSN is less than 4 Char or not captured by OCR'
                            whold_tax_rate_inv = 'HSN is less than 4 Char or not captured by OCR'
                        else:
                            whold_tax_section_inv = '194Q'
                            whold_tax_rate_master_data_inv = withholdingtaxMastersData.objects.filter(company_id=company,wtaxsection='194Q').first()
                            whold_tax_rate_inv = whold_tax_rate_master_data_inv.wtaxcoderate
                else:
                    whold_tax_section_inv = 'HSN is not captured by OCR'
                    whold_tax_rate_inv = 'HSN is not captured by OCR'  
            
            tds_rate = {}
            tds_section = {}
            tds_rate['Invoice Data'] = whold_tax_rate_inv
            tds_rate['Master Data'] = whold_tax_rate_master
            tds_rate['Status'] = 'Matched'
            try:
                if int(float(whold_tax_rate_inv)) != int(float(whold_tax_rate_master)):
                    tds_rate['Status'] = 'Not Matched'
                    color_6 = 'r'
            except:
                tds_rate['Status'] = 'Not Matched'
                color_6 = 'r'

            tds_section['Invoice Data'] = whold_tax_section_inv
            tds_section['Master Data'] = whold_tax_section_master
            tds_section['Status'] = 'Matched'
            if whold_tax_section_inv != whold_tax_section_master:
                tds_section['Status'] = 'Not Matched'
                color_6 = 'r'
            
            withholdtax_code['tds_rate'] = tds_rate
            withholdtax_code['tds_section'] = tds_section
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()
        try:
            vendor_pan['Status'] = 'Okay'
            vendor_pan['reason'] = ''
            if tax_check.get('Vendor_Pan_Active',{}).get('status')!='Okay':
                vendor_pan['Status'] = tax_check.get('Vendor_Pan_Active',{}).get('status')
                vendor_pan['reason'] = tax_check.get('Vendor_Pan_Active',{}).get('Gst_Portal')
                count = count - 1
            adhar_pan_link['Status'] = 'Okay'
            adhar_pan_link['reason'] = ''
            if tax_check.get('Vendor_Pan-Adhar_Linked',{}).get('status')!='Okay':
                adhar_pan_link['Status'] = tax_check.get('Vendor_Pan-Adhar_Linked',{}).get('status')
                adhar_pan_link['reason'] = tax_check.get('Vendor_Pan-Adhar_Linked',{}).get('Gst_Portal')
                count = count - 1
            _206Ab['Status'] = 'Okay'
            _206Ab['reason'] = ''
            if tax_check.get('Vendor_206AB',{}).get('status')!='active':
                _206Ab['Status'] = tax_check.get('Vendor_206AB',{}).get('status')
                _206Ab['reason'] = tax_check.get('Vendor_206AB',{}).get('Gst_Portal')
                count = count - 1
            if count == 3:
                withholdtax_check['color'] = 'o' 
            elif count <3:
                withholdtax_check['color'] = 'r'
            else:
                withholdtax_check['color'] = 'g'
        except Exception as e:
            print(f"Error {e}")
            traceback.print_exc()


        r6_checks = {}
        r6_checks['Vendor Defaulter u/s 206AB'] = _206Ab
        r6_checks['Vendor PAN Active'] = vendor_pan
        r6_checks['Vendor Aadhar & PAN linked (For Individuals)'] = adhar_pan_link
        data_r6 = {}
        data_r6['Pan Check'] = r6_checks
        data_r6['With Hold Tax Check'] = withholdtax_code

        withholdtax_check['data'] = data_r6
        
        withholdtax_check['message'] = 'Withholding Tax Check'
        
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()

    ## accounting check----> radiobutton7
    account_check = {}
    count = 5
    account_check_data = {}
    try:
        account_check_data['Company Code'] = migo_data[0].row_data.get(field_map['CompanyCode'])
        if migo_data[0].row_data.get(field_map['CompanyCode']):
            account_check_data['Company Code'] = migo_data[0].row_data.get(field_map['CompanyCode'])
            count = count - 1
        account_check_data['posting_date'] = configurations['posting_date']
        if configurations['posting_date']:
            account_check_data['posting_date'] = configurations['posting_date']
            count = count - 1
        account_check_data['Currency'] = invoice_data.get('Currency')
        if invoice_data.get('Currency'):
            account_check_data['Currency'] = invoice_data.get('Currency')
            count = count - 1
        account_check_data['GL Account'] = migo_data[0].row_data.get(field_map['GLAccount'])
        if migo_data[0].row_data.get(field_map['GLAccount']):
            account_check_data['GL Account'] = migo_data[0].row_data.get(field_map['GLAccount'])
            count = count - 1
        account_check_data['Cost Center'] = migo_data[0].row_data.get(field_map['CostCenter'])
        if migo_data[0].row_data.get(field_map['CostCenter']):
            account_check_data['Cost Center'] = migo_data[0].row_data.get(field_map['CostCenter'])
            count = count - 1
        if count == 1:
            account_check['color'] = 'o' 
        elif count >1:
            account_check['color'] = 'r'
        else:
            account_check['color'] = 'g'
        account_check['message'] = 'Accounting Check'
        account_check['data'] = account_check_data
    except Exception as e:
        print(f"Error {e}")
        traceback.print_exc()
    # Assign to radio checks
    radio_checks['r1'] = invoice_calulation_matching_check
    radio_checks['r2'] = complete_invoice_
    # radio_checks['r3'] = duplicate_check
    radio_checks['r4'] = valid_vendor
    radio_checks['r5'] = gsttax_check
    radio_checks['r6'] = withholdtax_check
    radio_checks['r7'] = account_check

    return radio_checks

def configuration_setting(company,api_response_):
    invoice_data = api_response_.get('result').get('Invoice_data')
    tax_check = api_response_.get('result').get('CHECKS').get('tax_check')
    vendor_gst = invoice_data.get('Vendor Gst No.')
    invoice_num = invoice_data.get('InvoiceId')
    invoice_num = re.sub(r'[^A-Za-z0-9]', '', invoice_num)
    config = Configurations.objects.filter(company_id=company).first()
    # print(company,vendor_gst)
    vendor_master_data = VendorMastersData.objects.filter(company_id=company,GSTNo=vendor_gst).first()
    # print(vendor_master_data)
    vendorcode = vendor_master_data.VendorCode
    wtax_code = vendor_master_data.LDCWTCode
    migo_data = OpenGRNData.objects.filter(company_id=company,vendor_code=vendorcode,inv_no=invoice_num)
    
    # Build a dict of {system_var: miro_header}
    configurations = {}
    if config:
        monthly_close = config.monthly_close
        if monthly_close.get('monthly_close') == 'N':
            posting_date_type = monthly_close.get('date_of_entry')
            if posting_date_type == 'system':
                configurations['posting_date'] = date.today().strftime('%Y-%m-%d')
            elif posting_date_type == 'invoice':
                configurations['posting_date'] = invoice_data.get('InvoiceDate')
            else:
                configurations['posting_date'] = invoice_data.get('InvoiceDate')
        else:
            pass
        baseline_config = config.baseline
        if baseline_config.get('baseline_active') == 'Y':
            baselinedt_type = baseline_config.get('baseline_choice')
            if baselinedt_type == 'system':
                configurations['posting_date'] = date.today().strftime('%Y-%m-%d')
            elif baselinedt_type == 'invoice':
                configurations['BaselineDate'] = invoice_data.get('InvoiceDate')
            else:
                configurations['BaselineDate'] = invoice_data.get('InvoiceDate')

        blocking_config = config.blocking
        if blocking_config:
            filtered_blocking = {
                key: value
                for key, value in blocking_config.items()
                if value.get('acc') == 'Y' or value.get('pay') == 'Y'
            }
            block_acc = {'action': 'N', 'reason': ''}
            block_pay = {'action': 'N', 'reason': ''}

            checks = {
                'pan_inactive': ('Vendor_Pan_Active', 'Not Okay'),
                'gst_inactive': ('Vendor_Gst_Active', 'NO'),
                'aadhar_pan': ('Vendor_Pan-Adhar_Linked', 'Not Okay'),
                'gstr1': ('Vendor_Filing_status', 'Not Okay'),
                'gstr3b': ('Vendor_Filing_status', 'Not Okay'),
                'regular_vendor': ('Vendor_TaxPayer_type', 'Regular'),
                'regular_vendor': ('Vendor_TaxPayer_type', 'Regular')
            }
            account_block_indicator = ''
            payment_block_indicator = ''
            for key, value in filtered_blocking.items():
                if key not in checks:
                    continue

                tax_key, expected_status = checks[key]
                actual_status = tax_check.get(tax_key, {}).get('status')
                # print(key,expected_status,actual_status)
                # Handle "regular_vendor" which blocks when status != 'Regular'
                condition_failed = (
                    (key == 'regular_vendor' and actual_status != expected_status)
                    or (key != 'regular_vendor' and actual_status == expected_status)
                )

                if condition_failed:
                    if value.get('acc') == 'Y':
                        if account_block_indicator != '':
                            account_block_indicator = account_block_indicator+','+value.get('code')
                        else:
                            account_block_indicator = value.get('code')
                        block_acc['action'] = account_block_indicator
                        block_acc['reason'] += f"{key}, "
                    if value.get('pay') == 'Y':
                        if payment_block_indicator != '':
                            payment_block_indicator = payment_block_indicator+','+value.get('code')
                        else:
                            payment_block_indicator = value.get('code')
                        block_pay['action'] = payment_block_indicator
                        block_pay['reason'] += f"{key}, "

            configurations['block_acc'] = block_acc
            configurations['block_pay'] = block_pay
            # print(configurations)
        curr_config = config.currency
        currency = {}
        if curr_config:
            currency['curr_code'] = curr_config.get('reporting_currency_code')
            currency['inv_curr'] = invoice_data.get('Currency')
            currency['reporting_curr'] = curr_config.get('reporting_currency_name')
            currency['exchange_rate_tolerance'] = curr_config.get('exchange_rate_tolerance')
        configurations['Currency'] = currency 

        narration_config = config.narration
        narration = ''

        if narration_config:
            fields = narration_config.get('fields', [])
            symbol = narration_config.get('symbol', ' ')
            
            # Mapping of config field name → invoice_data key
            field_map_narration = {
                'invoice_no': 'InvoiceId',
                'vendor_name': 'VendorName',
                'amount': 'InvoiceTotal',
                'date': 'InvoiceDate',
                'po_no': 'PurchaseOrder'
            }
            
            narration_parts = []
            for field in fields:
                key = field_map_narration.get(field)
                if key:
                    value = invoice_data.get(key)
                    if value not in (None, '', 'None'):
                        narration_parts.append(str(value))
            
            narration = symbol.join(narration_parts)

        configurations['narration'] = narration 

        matching_config = config.matching
        matching_result = {}
        if matching_config:
            typ = matching_config.get('matching_type')
            if typ == '2way':
                df1,result = _2way_match(company,migo_data,invoice_data)
                matching_result['matching type'] = '2way'
                matching_result['result'] = result['status']
                matching_result['reason'] = result['reason']
                matching_result['table'] = df1
            elif typ == '3way':
                po_data = POData.objects.filter(company_id=company,vendor_code=vendorcode,inv_no=invoice_num)
                if po_data:
                    df1,result = _3way_match(company,migo_data,po_data,invoice_data)
                    matching_result['matching type'] = '3way'
                    matching_result['result'] = result['status']
                    matching_result['reason'] = result['reason']
                    matching_result['table'] = df1
                else:
                    df1,result = _2way_match(company,migo_data,invoice_data)
                    matching_result['matching type'] = '2way'
                    matching_result['result'] = result['status']
                    matching_result['reason'] = result['reason']
                    matching_result['table'] = df1
        configurations['2/3_Way_Matching'] = matching_result

        #### withholding tax calculation
        wtaxcode_config = config.threshold
        withhold_tax = {}
        normal_withholding_tax_rate = 0
        ldc_withholding_tax_rate = 0
        tds_val = 0
        if wtaxcode_config:
            applicable = wtaxcode_config.get('turnover_above_threshold')
            try:
                if applicable == 'Y':
                    current_inv_value = invoice_data.get('SubTotal')
                    normal_record = withholdingtaxMastersData.objects.filter(company_id=company, wtaxcode=wtax_code, ldc='N').first()
                    all_inv_total= VendorsTotals.objects.filter(company=company,Vendor_code=vendorcode).aggregate(total=Sum('inv_value'))['total'] or 0
                    normal_withholding_tax_rate = wtaxcode_config.get('wt_rate')
                    if float(all_inv_total) + float(current_inv_value) > float(wtaxcode_config.get('threshold_amount')):
                        if vendor_master_data.LDCNo:
                            ldc_start_date = vendor_master_data.LDCStartDate
                            ldc_end_date = vendor_master_data.LDCEndDate
                            inv_date = invoice_data.get('InvoiceDate')  #'2025-03-31'
                            
                            
                            threshold = vendor_master_data.LDCThreshold
                            # Convert all dates to datetime objects
                            try:
                                # print(ldc_start_date, ldc_end_date, inv_date)
                                # Safely parse possible datetime strings
                                def parse_date_safe(date_str):
                                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
                                        try:
                                            return datetime.strptime(str(date_str).strip(), fmt)
                                        except ValueError:
                                            continue
                                    raise ValueError(f"Unsupported date format: {date_str}")

                                ldc_start = parse_date_safe(ldc_start_date)
                                ldc_end = parse_date_safe(ldc_end_date)
                                inv_dt = parse_date_safe(inv_date)
                                
                                # Check if invoice date falls in range
                                if ldc_start <= inv_dt <= ldc_end:
                                    # print('wtax_code--->',wtax_code)
                                    ldc_record = withholdingtaxMastersData.objects.filter(company_id=company, wtaxcode=wtax_code, ldc='Y').first()
                                    ldc_withholding_tax_rate = float(ldc_record.ldtrate) if ldc_record else 0
                                    
                                    # print("Invoice date falls within LDC period.")
                                else:
                                    print("Invoice date is outside LDC period.")
                            except Exception as e:
                                print("Error parsing dates:", e)
                                traceback.print_exc()
                            # print('normal rate-->',normal_withholding_tax_rate)
                            # print('lower rate-->',ldc_withholding_tax_rate)
                            try:
                                # Ensure all inputs are numeric
                                threshold = float(threshold or 0)
                                all_inv_total = float(all_inv_total or 0)
                                current_inv_value = float(current_inv_value or 0)
                                normal_withholding_tax_rate = float(normal_withholding_tax_rate or 0)
                                ldc_withholding_tax_rate = float(ldc_withholding_tax_rate or 0)
                                

                                # print(threshold,all_inv_total,current_inv_value)
                                # print(normal_withholding_tax_rate,ldc_withholding_tax_rate)

                                if threshold > 0:
                                    # print('threshold-->',threshold)
                                    # print('all_inv_total-->',all_inv_total)
                                    # print('current_inv_value-->',current_inv_value)
                                    # Case 1 and 2
                                    if threshold > all_inv_total:
                                        if threshold >= all_inv_total + current_inv_value:
                                            # Case 1: entire current invoice is below threshold
                                            tds_val = current_inv_value * (ldc_withholding_tax_rate/100)
                                        else:
                                            # Case 2: part of invoice crosses threshold
                                            tds_val = ((threshold - all_inv_total) * (ldc_withholding_tax_rate/100)) + \
                                                    ((all_inv_total + current_inv_value - threshold) * (normal_withholding_tax_rate/100))
                                    else:
                                        # Case 3: threshold already exceeded
                                        tds_val = current_inv_value * (normal_withholding_tax_rate/100)
                                else:
                                    # No threshold, apply rate2 directly
                                    tds_val = current_inv_value * (normal_withholding_tax_rate/100)

                            except Exception as e:
                                print(f"Error calculating TDS: {e}")
                                traceback.print_exc()
                                tds_val = 0  
                                        
                        else:
                            ldc_withholding_tax_rate = 0
                            normal_withholding_tax_rate = 0
                            # print(current_inv_value,current_inv_value)
                            tds_val = 0
            except Exception as e:
                print(f"Error calculating TDS: {e}")
                traceback.print_exc()
                tds_val = 0      
                
        withhold_tax['WithHolding Tax Rate till Threshold'] = ldc_withholding_tax_rate 
        withhold_tax['WithHolding Tax Rate after Threshold'] = normal_withholding_tax_rate
        withhold_tax['WithHolding Tax value'] = tds_val
        configurations['WithHolding Tax Details'] = withhold_tax 

        currency_config = config.currency
        exchange_rate = 1
        if curr_config:
            reporting_currency = currency_config.get('reporting_currency_code') 
            exchange_rate_tolerance = currency_config.get('exchange_rate_tolerance')  
            inv_currency = invoice_data.get('Currency')   
            if reporting_currency.strip() != inv_currency:
                exchange_rate = get_exchange_rate(inv_currency,reporting_currency) 
        configurations['exchange_rate'] = exchange_rate    
                    
    else:
        print("No configuration found for this company.")
    print(configurations)
    return configurations
def _3way_match(company,migo_data,po_data,invoice_data):
    result = {}
    try:
        try:
            grn_description = SystemVariableMapping.objects.get(
                company=company, system_var='item_descritption'
            ).miro_header
            grn_qty = SystemVariableMapping.objects.get(
                company=company, system_var='Qty_Invoiced'
            ).miro_header
            grn_rate = SystemVariableMapping.objects.get(
                company=company, system_var='item_rate'
            ).miro_header
            # inv_num_header = SystemVariableMapping.objects.get(
            #     company=company, system_var='SuppInv_no'
            # ).miro_header
        except SystemVariableMapping.DoesNotExist:
            result['status'] = 'Not Okay'
            result['reason'] = "Required columns not mapped in Migo Data or not found"
            return '',result

        
        table_data = invoice_data.get('Invoice items:')
        list_data = [v for k, v in table_data.items()]
        df1 = pd.DataFrame(list_data)
        required_cols = ['item_description', 'item_quantity', 'unit_price']

        # Check if all required columns are present
        if all(col in df1.columns for col in required_cols):
            df1 = df1[required_cols]
        else:
            result['status'] = 'Not Okay'
            result['reason'] = "Required columns not present in invoice table"
            return '',result

        grn_table_data = []
        
        if migo_data:
            for record in migo_data:
                grn_data ={}
                row = record.row_data
                grn_data['grn_description'] = row.get(grn_description)
                grn_data['grn_qty'] = row.get(grn_qty)
                grn_data['grn_rate'] = row.get(grn_rate)
                grn_table_data.append(grn_data)
        # print(grn_table_data)
        if grn_table_data:
            df2 = pd.DataFrame(grn_table_data)
        else:
            result['status'] = 'Not Okay'
            result['reason'] = "Data not found in open grn records"
            return '',result
        
        invoice_grn_df,d2 = map_rows(df1,df2,'invoice_migo')

        try:
            po_description = SystemVariableMapping.objects.get(
                company=company, system_var='item_descritption'
            ).po_header
            po_qty = SystemVariableMapping.objects.get(
                company=company, system_var='Qty_Invoiced'
            ).po_header
            po_rate = SystemVariableMapping.objects.get(
                company=company, system_var='item_rate'
            ).po_header
            # inv_num_header = SystemVariableMapping.objects.get(
            #     company=company, system_var='SuppInv_no'
            # ).miro_header
        except SystemVariableMapping.DoesNotExist:
            result['status'] = 'Not Okay'
            result['reason'] = "Required columns not mapped in PO Data or not found"
            return '',result
        po_table_data = []
        for record in po_data:
            po_data_ ={}
            row = record.row_data
            po_data_['grn_description'] = row.get(po_description)
            po_data_['grn_qty'] = row.get(po_qty)
            po_data_['grn_rate'] = row.get(po_rate)
            po_table_data.append(po_data_)
        if grn_table_data:
            df3 = pd.DataFrame(po_table_data)

        invoice_grn_po_df,d2 = map_rows(invoice_grn_df,df3,'invoice_migo_po')
        # print(d1.columns)
        cols_to_move = ['matching%', 'color', 'status']
        invoice_grn_po_df = invoice_grn_po_df[[c for c in invoice_grn_po_df.columns if c not in cols_to_move] + cols_to_move]
        # print(df1)
        if (invoice_grn_po_df['status'] == 'matched').all():
            result['status'] = 'Okay'
            result['reason'] = " "
            # print(d1,result)
            return invoice_grn_po_df ,result
        else:
            # print(d1,result)
            result['status'] = 'Not Okay'
            result['reason'] = " "
            return invoice_grn_po_df ,result
    except:
        import traceback
        traceback.print_exc()

def _2way_match(company,migo_data,invoice_data):
    result = {}
    try:
        try:
            grn_description = SystemVariableMapping.objects.get(
                company=company, system_var='item_descritption'
            ).miro_header
            grn_qty = SystemVariableMapping.objects.get(
                company=company, system_var='Qty_Invoiced'
            ).miro_header
            grn_rate = 'UnitPrice'
            # inv_num_header = SystemVariableMapping.objects.get(
            #     company=company, system_var='SuppInv_no'
            # ).miro_header
        except SystemVariableMapping.DoesNotExist:
            result['status'] = 'Not Okay'
            result['reason'] = "Required columns not mapped in Migo Data or not found"
            return '',result

        
        table_data = invoice_data.get('Invoice items:')
        list_data = [v for k, v in table_data.items()]
        df1 = pd.DataFrame(list_data)
        required_cols = ['item_description', 'item_quantity', 'unit_price']

        # Check if all required columns are present
        if all(col in df1.columns for col in required_cols):
            df1 = df1[required_cols]
        else:
            result['status'] = 'Not Okay'
            result['reason'] = "Required columns not present in invoice table"
            return '',result

        grn_table_data = []
        
        if migo_data:
            for record in migo_data:
                grn_data ={}
                row = record.row_data
                grn_data['grn_description'] = row.get(grn_description)
                grn_data['grn_qty'] = row.get(grn_qty)
                grn_data['grn_rate'] = row.get(grn_rate)
                grn_table_data.append(grn_data)
        # print(grn_table_data)
        if grn_table_data:
            df2 = pd.DataFrame(grn_table_data)
        else:
            result['status'] = 'Not Okay'
            result['reason'] = "Data not found in open grn records"
            return '',result
        
        invoice_grn_df,d2 = map_rows(df1,df2,'invoice_migo')
        # print(d1.columns)
        cols_to_move = ['matching%', 'color', 'status']
        invoice_grn_df = invoice_grn_df[[c for c in invoice_grn_df.columns if c not in cols_to_move] + cols_to_move]
        # print(df1)
        if (invoice_grn_df['status'] == 'matched').all():
            result['status'] = 'Okay'
            result['reason'] = " "
            # print(d1,result)
            return invoice_grn_df ,result
        else:
            # print(d1,result)
            result['status'] = 'Not Okay'
            result['reason'] = " "
            return invoice_grn_df ,result
    except:
        import traceback
        traceback.print_exc()
    
def template_setting_view(request):
    company = request.user.company_code
    mappingheader = TemplateMapping.objects.filter(company_code=company).first()

    templateheader1 = mappingheader.mapped_headers1 if mappingheader else {}
    templateheader2 = mappingheader.mapped_headers2 if mappingheader else {}

    # Extract system variable field names (excluding first 2 fields)
    system_vars = [field.name for field in InvoiceDetails._meta.get_fields()][3:] + ['None']
    # print(system_vars)
    # Pass to frontend
    return render(request, 'template_setting.html', {
        'templateheader1': list(templateheader1.keys()) if templateheader1 else [],
        'templateheader2': list(templateheader2.keys()) if templateheader2 else [],
        'system_vars': system_vars
    })

@csrf_exempt
def upload_headers(request):
    if request.method == 'POST' and request.FILES:
        company = request.user.company_code
        files = request.FILES
        responses = {}

        base_template_dir = os.path.join(settings.MEDIA_ROOT, "Template_files", str(company))
        os.makedirs(base_template_dir, exist_ok=True)

        # Count how many files user uploaded
        file_count = len(files)
        mapped_headers1, mapped_headers2 = {}, {}

        for file_key, uploaded_file in files.items():
            header_rows = int(request.POST.get(f'{file_key}_header_rows', 1))
            file_index = file_key.split('_')[-1]  # '1' or '2'
            base_filename = f"basetemplate{file_index}.xlsx"
            file_path = os.path.join(base_template_dir, base_filename)

            # ✅ Read file up to the specified header rows
            df = pd.read_excel(uploaded_file)

            # ✅ Always take only the *first* header row for mapping
            headers = [str(h) for h in df.columns.tolist()]
            # print(header_rows)
            # ✅ Save only those header rows (header + next row if header_rows = 2)
            df_header_only = pd.read_excel(uploaded_file, nrows=header_rows-1)
            df_header_only.to_excel(file_path, index=False)

            # ✅ Store headers as key=None (initial unmapped state)
            if file_index == '1':
                mapped_headers1 = {h: None for h in headers}
            elif file_index == '2':
                mapped_headers2 = {h: None for h in headers}

            responses[file_key] = headers

        # print(mapped_headers1,mapped_headers2)
        TemplateMapping.objects.update_or_create(
            company_code=company,
            defaults={
                'file_no': file_count,
                'mapped_headers1': mapped_headers1,
                'mapped_headers2': mapped_headers2,
            }
        )

        return JsonResponse({'status': 'success', 'headers': responses})

    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def template_header_mapping(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode('utf-8'))
            template_type = data.get("template_type")
            mapping = data.get("mapping")

            if not template_type or not mapping:
                return JsonResponse({"status": "error", "message": "Missing template_type or mapping"}, status=400)

            company = request.user.company_code

            # Fetch the record for this company
            # mapping_obj, created = TemplateMapping.objects.get_or_create(company_code=company)
            mapping_obj = TemplateMapping.objects.filter(company_code=company).first()

            # Update only the relevant field
            if template_type == "templateheader1":
                mapping_obj.mapped_headers1 = mapping
                field = 'mapped_headers1'
            elif template_type == "templateheader2":
                mapping_obj.mapped_headers2 = mapping
                field = 'mapped_headers2'
            else:
                return JsonResponse({"status": "error", "message": "Invalid template type"}, status=400)

            mapping_obj.save(update_fields=[field])  # only updates the changed field

            return JsonResponse({
                "status": "success",
                "message": f"Mapping for {template_type} saved successfully."
            })

        except Exception as e:
            print("Error:", e)
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

@csrf_exempt
def template_preview(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        invoice_keys = data.get("invoice_keys", [])
        company = request.user.company_code

        if not invoice_keys:
            return JsonResponse({"status": "error", "message": "No invoice keys provided"}, status=400)

        # ✅ Get mapping info for this company
        mapping_obj = TemplateMapping.objects.filter(company_code=company).first()
        if not mapping_obj:
            return JsonResponse({"status": "error", "message": "No Template Mapping found"}, status=404)

        file_no = mapping_obj.file_no
        mapped_headers1 = mapping_obj.mapped_headers1 or {}
        mapped_headers2 = mapping_obj.mapped_headers2 or {}

        # ✅ Fetch all matching invoices
        invoices = InvoiceDetails.objects.filter(company=company, invoice_key__in=invoice_keys)
        if not invoices.exists():
            return JsonResponse({"status": "error", "message": "No matching invoices found"}, status=404)

        invoice_data = list(invoices.values())

        # ✅ Prepare directories
        base_template_dir = os.path.join(settings.MEDIA_ROOT, "Template_files", str(company))
        
        

        # Helper function: Create DataFrame based on mapping
        def create_mapped_df(data_list, mapping):
            df_data = []
            for inv in data_list:
                row = {excel_col: inv.get(sys_field, "") for excel_col, sys_field in mapping.items()}
                df_data.append(row)
            return pd.DataFrame(df_data)

        responses = {}

        # ----------------------------------------------------------------------
        # 🧾 CASE 1: Single Template File (file_no = 1)
        # ----------------------------------------------------------------------
        if file_no == 1:
            
            base_path = os.path.join(base_template_dir, "basetemplate1.xlsx")

            # ✅ Prepare DataFrame for all invoice records (detailed)
            df_new = create_mapped_df(invoice_data, mapped_headers1)

            
            if not os.path.exists(base_path):
                return JsonResponse({"status": "error", "message": "Base template 1 not found"}, status=404)
            df_base = pd.read_excel(base_path)
            df_final = pd.concat([df_base, df_new], ignore_index=True)

            # df_final.to_excel(template_path, index=False)
            responses["templatefile1"] = df_final

        # ----------------------------------------------------------------------
        # 🧾 CASE 2: Two Template Files (file_no = 2)
        # ----------------------------------------------------------------------
        elif file_no == 2:
            
            base1_path = os.path.join(base_template_dir, "basetemplate1.xlsx")

            # One row per invoice (summary)
            summary_data = []
            seen_keys = set()
            for inv in invoice_data:
                key = str(inv["invoice_key"])
                if key not in seen_keys:
                    row = {excel_col: inv.get(sys_field, "") for excel_col, sys_field in mapped_headers1.items()}
                    summary_data.append(row)
                    seen_keys.add(key)
            df_summary = pd.DataFrame(summary_data)

            
            if not os.path.exists(base1_path):
                return JsonResponse({"status": "error", "message": "Base template 1 not found"}, status=404)
            df_base = pd.read_excel(base1_path)
            df_final1 = pd.concat([df_base, df_summary], ignore_index=True)

            
            responses["templatefile1"] = df_final1

            # FILE 2 → Detailed (all items for invoices)
            
            base2_path = os.path.join(base_template_dir, "basetemplate2.xlsx")

            df_detailed = create_mapped_df(invoice_data, mapped_headers2)

            
            
            if not os.path.exists(base2_path):
                return JsonResponse({"status": "error", "message": "Base template 2 not found"}, status=404)
            df_base2 = pd.read_excel(base2_path)
            df_final2 = pd.concat([df_base2, df_detailed], ignore_index=True)

            
            responses["templatefile2"] = df_final2

        else:
            return JsonResponse({"status": "error", "message": "Invalid file number"}, status=400)
        print(responses)
        # Convert DataFrames to HTML tables
        html_responses = {}
        for key, df in responses.items():
            html_responses[key] = df.to_html(index=False, border=1, classes="table table-bordered table-sm")

        return JsonResponse({"status": "success", "message": "Templates generated successfully", "template_html": html_responses})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def template_generate(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        invoice_keys = data.get("invoice_keys", [])
        company = request.user.company_code

        if not invoice_keys:
            return JsonResponse({"status": "error", "message": "No invoice keys provided"}, status=400)

        # ✅ Get mapping info for this company
        mapping_obj = TemplateMapping.objects.filter(company_code=company).first()
        if not mapping_obj:
            return JsonResponse({"status": "error", "message": "No Template Mapping found"}, status=404)

        file_no = mapping_obj.file_no
        mapped_headers1 = mapping_obj.mapped_headers1 or {}
        mapped_headers2 = mapping_obj.mapped_headers2 or {}

        # ✅ Fetch all matching invoices
        invoices = InvoiceDetails.objects.filter(company=company, invoice_key__in=invoice_keys)
        if not invoices.exists():
            return JsonResponse({"status": "error", "message": "No matching invoices found"}, status=404)

        invoice_data = list(invoices.values())

        # ✅ Prepare directories
        base_template_dir = os.path.join(settings.MEDIA_ROOT, "Template_files", str(company))
        generated_dir = os.path.join(settings.MEDIA_ROOT, "Generated_Templates", str(company))
        os.makedirs(generated_dir, exist_ok=True)

        # Helper function: Create DataFrame based on mapping
        def create_mapped_df(data_list, mapping):
            df_data = []
            for inv in data_list:
                row = {excel_col: inv.get(sys_field, "") for excel_col, sys_field in mapping.items()}
                df_data.append(row)
            return pd.DataFrame(df_data)

        responses = {}

        # ----------------------------------------------------------------------
        # 🧾 CASE 1: Single Template File (file_no = 1)
        # ----------------------------------------------------------------------
        if file_no == 1:
            template_path = os.path.join(generated_dir, "templatefile1.xlsx")
            base_path = os.path.join(base_template_dir, "basetemplate1.xlsx")

            # ✅ Prepare DataFrame for all invoice records (detailed)
            df_new = create_mapped_df(invoice_data, mapped_headers1)

            if os.path.exists(template_path):
                df_existing = pd.read_excel(template_path)
                df_final = pd.concat([df_existing, df_new], ignore_index=True)
            else:
                if not os.path.exists(base_path):
                    return JsonResponse({"status": "error", "message": "Base template 1 not found"}, status=404)
                df_base = pd.read_excel(base_path)
                df_final = pd.concat([df_base, df_new], ignore_index=True)

            # df_final.to_excel(template_path, index=False)
            responses["templatefile1"] = f"✅ Template 1 updated ({len(df_new)} rows added)"

        # ----------------------------------------------------------------------
        # 🧾 CASE 2: Two Template Files (file_no = 2)
        # ----------------------------------------------------------------------
        elif file_no == 2:
            # FILE 1 → Summary (1 row per invoice)
            template1_path = os.path.join(generated_dir, "templatefile1.xlsx")
            base1_path = os.path.join(base_template_dir, "basetemplate1.xlsx")

            # One row per invoice (summary)
            summary_data = []
            seen_keys = set()
            for inv in invoice_data:
                key = str(inv["invoice_key"])
                if key not in seen_keys:
                    row = {excel_col: inv.get(sys_field, "") for excel_col, sys_field in mapped_headers1.items()}
                    summary_data.append(row)
                    seen_keys.add(key)
            df_summary = pd.DataFrame(summary_data)

            if os.path.exists(template1_path):
                df_existing = pd.read_excel(template1_path)
                df_final1 = pd.concat([df_existing, df_summary], ignore_index=True)
            else:
                if not os.path.exists(base1_path):
                    return JsonResponse({"status": "error", "message": "Base template 1 not found"}, status=404)
                df_base = pd.read_excel(base1_path)
                df_final1 = pd.concat([df_base, df_summary], ignore_index=True)

            df_final1.to_excel(template1_path, index=False)
            responses["templatefile1"] = f"✅ Template 1 updated ({len(df_summary)} summary rows added)"

            # FILE 2 → Detailed (all items for invoices)
            template2_path = os.path.join(generated_dir, "templatefile2.xlsx")
            base2_path = os.path.join(base_template_dir, "basetemplate2.xlsx")

            df_detailed = create_mapped_df(invoice_data, mapped_headers2)

            if os.path.exists(template2_path):
                df_existing2 = pd.read_excel(template2_path)
                df_final2 = pd.concat([df_existing2, df_detailed], ignore_index=True)
            else:
                if not os.path.exists(base2_path):
                    return JsonResponse({"status": "error", "message": "Base template 2 not found"}, status=404)
                df_base2 = pd.read_excel(base2_path)
                df_final2 = pd.concat([df_base2, df_detailed], ignore_index=True)

            df_final2.to_excel(template2_path, index=False)
            responses["templatefile2"] = f"✅ Template 2 updated ({len(df_detailed)} detailed rows added)"

        else:
            return JsonResponse({"status": "error", "message": "Invalid file number"}, status=400)

        return JsonResponse({"status": "success", "message": "Templates generated successfully", "details": responses})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
    
@csrf_exempt
@login_required
def submit_pending_invoice(request):
    if request.method == "POST":
        company = request.user.company_code
        unique_name = request.POST.get("unique_name")
        updated_data = {
            "VendorGst": request.POST.get("VendorGst"),
            "VendorCode": request.POST.get("VendorCode"),
            "InvNo": request.POST.get("InvNo"),
            "CustomerGst": request.POST.get("CustomerGst"),
            "BasicAmount": request.POST.get("BasicAmount"),
            "TotalTax": request.POST.get("TotalTax"),
            "TotalAmount": request.POST.get("TotalAmount"),
        }

        try:
            invoice = PendingInvoices.objects.get(company_code=company, unique_name=unique_name)
            api_response = invoice.api_response
            invoice_path = invoice.path

            # Safely extract invoice_data
            invoice_data = api_response.get('result', {}).get('Invoice_data', {})

            # Update values
            invoice_data['InvoiceId'] = updated_data.get('InvNo')
            invoice_data['Vendor Gst No.'] = updated_data.get('VendorGst')
            invoice_data['Cutomer Gst No.'] = updated_data.get('CustomerGst')
            invoice_data['TotalTax'] = updated_data.get('TotalTax')
            invoice_data['SubTotal'] = updated_data.get('BasicAmount')
            invoice_data['InvoiceTotal'] = updated_data.get('TotalAmount')
            invoice_data['VendorCode'] = updated_data.get('VendorCode')
            invoice_data['formedit'] = True  # mark edited invoice

            api_response['result']['Invoice_data'] = invoice_data   # ✅ Correct place

            # Now call processing again
            processed = save_processed_invoice(api_response, invoice_path, unique_name, company)

            if processed is True:
                # If processing succeeded → DELETE from PendingInvoices
                invoice.delete()
                return JsonResponse({
                    "status": "success",
                    "message": "Invoice updated and processed successfully",
                    "updated": updated_data
                })

            else:
                # If processing failed again, keep pending.
                return JsonResponse({
                    "status": "warning",
                    "message": "Invoice updated but still incomplete. Please review again.",
                    "updated": updated_data
                })

        except PendingInvoices.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Invoice not found"})
    return JsonResponse({"status": "error", "message": "Invalid request method"})

def unallocatedcost_gl_view(request):
    company = request.user.company_code
    header_obj, created = Header.objects.get_or_create(company_id=company)

    # GET → Show page
    if request.method == "GET":
        gl_list = header_obj.unalloacatedcost_gl or []
        return render(request, "unallocatedcost_gl.html", {"gl_list": gl_list})

    # POST → Add GL codes
    if request.method == "POST":
        new_gl = request.POST.get("new_gl", "")
        file = request.FILES.get("gl_file")

        existing_gl = set(header_obj.unalloacatedcost_gl or [])

        # Upload via Excel
        if file:
            try:
                df = pd.read_excel(file)
                if 'GL' not in df.columns:
                    return JsonResponse({"status": "error", "message": "Excel must contain 'GL' column"})
                new_codes = set(df['GL'].astype(str).str.strip().tolist())
                existing_gl.update(new_codes)
            except Exception as e:
                return JsonResponse({"status": "error", "message": str(e)})

        # Add comma-separated input
        if new_gl:
            new_codes = set([x.strip() for x in new_gl.split(",") if x.strip()])
            existing_gl.update(new_codes)

        header_obj.unalloacatedcost_gl = list(existing_gl)
        header_obj.save()
        return redirect("/unallocatedcost-gl/")

def delete_gl_code(request, code):
    company = request.user.company_code
    header_obj = Header.objects.filter(company_id=company).first()
    if header_obj:
        codes = set(header_obj.unalloacatedcost_gl or [])
        codes.discard(code)
        header_obj.unalloacatedcost_gl = list(codes)
        header_obj.save()
    return redirect("/unallocatedcost-gl/")


def get_role_matrix(request):
    try:
        company = request.user.company_code
        obj = RoleMatrix.objects.filter(company_id=company).first()

        field_parameters = [
            "InvoiceDate", "ExchangeRate", "TaxCode", "WithholdingTaxCode",
            "Narration", "VendorGst", "UnplannedDeliveryCost"
        ]

        radio_parameters = [
            {"parameter": "3Way/2Way Match", "sub": ["2/3 way Match", "Invoice Calculation", "Other Checks"]},
            {"parameter": "Complete Invoice", "sub": ["Name & Address Check", "Other Parameter Check"]},
            {"parameter": "Valid Vendor", "sub": ["Valid Vendor Check"]},
            {"parameter": "GST Check", "sub": ["Tax Check", "E Way Check", "E Invoice Check"]},
            {"parameter": "With Holding Check", "sub": ["PAN Check", "With Holding Check"]},
            {"parameter": "Accounting Check", "sub": ["Accounting Check"]},
        ]

        def merge_field_matrix(saved_matrix, parameters):
            if not isinstance(saved_matrix, list):
                saved_matrix = []
            saved_dict = {item.get("parameter"): item for item in saved_matrix}

            return [
                saved_dict.get(p, {
                    "parameter": p,
                    "processor_edit": False,
                    "checker_approval": False,
                    "checker_edit": False
                })
                for p in parameters
            ]

        def merge_radio_matrix(saved_matrix, parameters):
            if not isinstance(saved_matrix, list):
                saved_matrix = []
            saved_dict = {item["parameter"]: item for item in saved_matrix}

            merged = []
            for row in parameters:
                p = row["parameter"]
                sub_items = row["sub"]

                saved_row = saved_dict.get(p, {})

                merged.append({
                    "parameter": p,
                    "sub": [
                        {
                            "name": sub,
                            "checker_approval": next(
                                (x["checker_approval"] for x in saved_row.get("sub", []) if x["name"] == sub),
                                False
                            )
                        }
                        for sub in sub_items
                    ]
                })

            return merged

        all_matrices = {
            "field_matrix": merge_field_matrix(getattr(obj, "field_matrix", []), field_parameters),
            "radio_matrix": merge_radio_matrix(getattr(obj, "radio_matrix", []), radio_parameters),
        }

        return JsonResponse({"matrices": all_matrices})

    except Exception as e:
        import traceback
        print("Error in get_role_matrix:", traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)




def save_role_matrix(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            matrix_type = data.get("matrix_type")
            matrix = data.get("matrix", [])
            # print(matrix)
            if matrix_type not in ["field_matrix", "radio_matrix"]:
                return JsonResponse({"error": "Invalid matrix type"}, status=400)

            # ✅ Get or create RoleMatrix record for this company
            company = request.user.company_code
            # obj, _ = RoleMatrix.objects.get_or_create(company_id=company)
            obj = RoleMatrix.objects.filter(company_id=company).first()
            if obj:
                # ✅ Update existing record
                setattr(obj, matrix_type, matrix)
                obj.save()
            else:
                # ✅ Create new record with all other fields empty
                obj = RoleMatrix.objects.create(
                    company=company,
                    field_matrix=matrix if matrix_type == "field_matrix" else {},
                    radio_matrix=matrix if matrix_type == "radio_matrix" else {},
                    unalloactedcost_matrix=matrix if matrix_type == "unalloactedcost_matrix" else {},
                    currency_matrix=matrix if matrix_type == "currency_matrix" else {},
                )
                

            return JsonResponse({
                "message": f"{matrix_type.replace('_', ' ').title()} saved successfully."
            })

        except Exception as e:
            import traceback
            print("❌ Error saving role matrix:", traceback.format_exc())
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid method"}, status=400)

@csrf_exempt
def update_remark(request):
    try:
        data = json.loads(request.body)
        unique_key = data.get("uniqueKey")
        role = data.get("role")
        key = data.get("key")
        sectionKey = data.get("sectionKey")
        updated_data = data.get("updated_data")
        print('data-->',data)
        print('key-->',key)
        print('unique_key-->',unique_key)
        print('sectionKey-->',sectionKey)
        print(updated_data)
        # Here you can update your record in DB
        # Example:
        obj = InvoiceSummary.objects.get(InvoiceGroupKey=unique_key)
        # 2️⃣ Load the InvoiceCheck dict (already a dict)
        invoice_check = obj.InvoiceCheck
        print("original invoice check -->",invoice_check)
        radio_field_changes = obj.radio_matrix_change or []
        # 3️⃣ Update only the relevant key (e.g. "r6")
        if role == 'processor':
            if key in invoice_check:
                change_dict = {}
                # Step A: Parse the JSON string into dict
                current_data = invoice_check[key]['data']
                if isinstance(current_data, str):
                    current_data = json.loads(current_data)

                # Step B: Update only the required section
                # Here sectionKey is the parent key, e.g. "Invoice Calculation2"
                # updated_data contains the corrected child-level data
                current_data[sectionKey] = updated_data

                # Step C: Save back as JSON string
                invoice_check[key]['data'] = json.dumps(current_data)

                # Step D: Update color for the section
                invoice_check[key]['color'] = 'y'
                change_dict['key'] = key
                change_dict['section'] = sectionKey
                radio_field_changes.append(change_dict)
                print(f"✅ Updated data for key: {key}")
            else:
                print(f"⚠️ Warning: Key {key} not found in InvoiceCheck")
        else:
            invoice_check[key]['data'] = json.dumps(updated_data)
        
        print("updated invoice check -->",invoice_check[key])
        # 4️⃣ Save changes back
        obj.InvoiceCheck = invoice_check
        obj.radio_matrix_change = radio_field_changes
        obj.save()
        obj.save(update_fields=["InvoiceCheck", "radio_matrix_change"])

        print("✅ InvoiceCheck updated successfully")

        return JsonResponse({"message": f"Remark updated successfully for {role}."})
    except Exception as e:
        print("Error updating remark:", e)
        return JsonResponse({"error": str(e)}, status=500)
    
@csrf_exempt  # (or use CSRF token properly in AJAX)
def get_invoice_details(request):
    if request.method == "POST":
        data = json.loads(request.body)
        group_key = data.get("InvoiceGroupKey")
        Tab = data.get("Tab")
        print(Tab)
        company = request.user.company_code  # already available in your session  
        if Tab == 'no_data':
            try:
                invoice = MissingDataInvoices.objects.get(InvoiceGroupKey=group_key)
                invoice_data = {
                    "VendorName": invoice.VendorName,
                    "InvoiceNo": invoice.InvNo,
                    "VendorGst": invoice.VendorGst,
                    "VendorCode": invoice.VendorCode,
                    # add other fields you need in your popup form 
                }
                return JsonResponse(invoice_data, safe=False)
            except MissingDataInvoices.DoesNotExist:
                return JsonResponse({"error": "Invoice not found"}, status=404)
        elif Tab == 'waiting_data':
            try:
                invoice = InvoiceSummary.objects.get(InvoiceGroupKey=group_key)
            except InvoiceSummary.DoesNotExist:
                return JsonResponse({"error": "Invoice not found"}, status=404)
        else: 
            try:
                invoice = InvoiceSummary.objects.get(InvoiceGroupKey=group_key)
            except InvoiceSummary.DoesNotExist:
                return JsonResponse({"error": "Invoice not found"}, status=404)
        config = Configurations.objects.get(company=company)
        currency_config = config.currency
        reporting_curr = currency_config.get('reporting_currency_code')
        exchange_tolerance = currency_config.get('exchange_rate_tolerance')
        inv_curr = invoice.InvCurrency
        exchange_edit = 'false'
        current_exch = 1
        ex_tolerance_message = None
        if reporting_curr != inv_curr:
            current_exch = get_exchange_rate(inv_curr, reporting_curr)
            tolerance = ((abs(float(current_exch)-float(invoice.ExchangeRate)))/float(invoice.ExchangeRate))*100
            if tolerance > exchange_tolerance:
                ex_tolerance_message = "Current Exchange Rate is out of tolerance level from Migo Exchange rate"
            exchange_edit = 'true'
        print(inv_curr,reporting_curr,current_exch)
        # ✅ Prepare clean, serializable dict
        invoice_data = {
            "VendorName": invoice.VendorName,
            "InvoiceNo": invoice.InvoiceNo,
            "InvoiceDate": str(invoice.InvoiceDate),
            "InvoiceValue": str(invoice.InvoiceValue),
            "InvoiceGroupKey": invoice.InvoiceGroupKey,
            "ExchangeRate": invoice.ExchangeRate,
            "CurrentExchangeRate": current_exch,
            "exchange_edit": exchange_edit,
            "ex_tolerance_message": ex_tolerance_message,
            "TaxCode": invoice.TaxCode,
            "VendorGst": invoice.VendorGst,
            "WithholdingTaxCode": invoice.WithholdingTaxCode,
            "Narration": invoice.Narration,
            "Updated_Data": invoice.original_data,
            # add other fields you need in your popup form
        }

        return JsonResponse(invoice_data, safe=False)
    
@csrf_exempt  # (or use CSRF token properly in AJAX)
def update_invoice_details(request):
    if request.method == "POST":
        data = json.loads(request.body)
        group_key = data.get("InvoiceGroupKey")
        try:
            invoice = InvoiceSummary.objects.get(InvoiceGroupKey=group_key)
        except InvoiceSummary.DoesNotExist:
            return JsonResponse({"error": "Invoice not found"}, status=404)

        # Already stored original values
        original_data = invoice.original_data or {}

        # New original_data sent from frontend
        original_data_from = data.get("original_data", {})

        # Merge new original keys only if not already present
        for key, value in original_data_from.items():
            dict_ = {}
            if key not in original_data:
                dict_['original'] = value
                original_data[key] = dict_

        
        # print(data)
        # print('data from front end', original_data_from)
        # print('original data from db',original_data)
        
        skip_keys = ['section','InvoiceGroupKey','original_data']
        changed_keys = invoice.field_matrix_change or []
        for key, new_value in data.items():
            dict_ = {}
            if key not in skip_keys:
                old_value = original_data.get(key,{}).get('original')

                # Case 1: Key did not exist OR old value is None → treat as changed if user entered something
                if old_value is None:
                    if new_value not in (None, "", [], {}):
                        dict_['original'] = original_data_from.get(key)
                        dict_['updated'] = new_value
                        original_data[key] = dict_
                        if key not in changed_keys:
                            changed_keys.append(key)
                    
                    continue

                # Case 2: Key exists → compare normally
                if old_value != new_value:
                    dict_['original'] = original_data_from.get(key)
                    dict_['updated'] = new_value
                    original_data[key] = dict_
                    if key not in changed_keys:
                        changed_keys.append(key)

        # print(changed_keys)
        # Save updated JSON field
        invoice.original_data = original_data
        invoice.field_matrix_change = changed_keys
        invoice.save(update_fields=["original_data", "field_matrix_change"]) 
        return JsonResponse({"message": f"Fields updated successfully for {group_key}."})
    
@csrf_exempt
def lookup_vendor_by_gst(request):
    data = json.loads(request.body.decode("utf-8"))
    gst_no = data.get("gst_number")
    company = request.user.company_code  # already available in your session

    vendor = VendorMastersData.objects.filter(
        company=company,
        GSTNo=gst_no
    ).first()

    if vendor:
        return JsonResponse({
            "found": True,
            "vendor_code": vendor.VendorCode,
            "vendor_name": vendor.VendorName
        })
    else:
        return JsonResponse({"found": False})

def approve_invoice(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)
    role = request.user.role  # already available in your session
    company = request.user.company_code  # already available in your session
    data = json.loads(request.body)
    invoice_key = data.get("invoice_group_key")
    # print(role)
    print(data)
    # print("Received InvoiceGroupKey:", invoice_key)
    param_matching = {'r1':"3Way/2Way Match",
                      'r2':"Complete Invoice",
                      'r3':"Duplicate Check",
                      'r4':"Valid Vendor",
                      'r5':"GST Check",
                      'r6':"With Holding Check",
                      'r7':"Accounting Check",}
    try:
        invoice = InvoiceSummary.objects.get(InvoiceGroupKey=invoice_key)
    except InvoiceSummary.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Invoice not found"
        }, status=404)
    if role == 'Processor':
        
        try:
            role_matrix = RoleMatrix.objects.filter(company_id=company).first()
        except InvoiceSummary.DoesNotExist:
            return JsonResponse({
                "status": "error",
                "message": "Role Matrix not found"
            }, status=404)
        requires_checker = False
        approval_req_field = []     # <-- new list
        approval_req_radio = []     # <-- new list
        field_matrix_change = invoice.field_matrix_change
        radio_matrix_change = invoice.radio_matrix_change

        rolematrix_field = role_matrix.field_matrix
        rolematrix_radio = role_matrix.radio_matrix
       
        # --- 1) Check field changes ---
        for changed_field in field_matrix_change:
            for config in rolematrix_field:
                if config["parameter"] == changed_field:
                    if config.get("checker_approval", False):
                        requires_checker = True
                        approval_req_field.append(changed_field)
                    # do NOT break, check entire config list
                    # (in case parameter appears multiple times)


        # --- 2) Check radio changes ---
        # print('radio_matrix_change-->', radio_matrix_change)
        # print('rolematrix_radio-->', rolematrix_radio)
        for change in radio_matrix_change:
            key = change["key"]              # r1, r2, r3...
            subsection = change["section"]   # Name of subsection

            # Map r1->"3Way/2Way Match" etc.
            parameter_name = param_matching.get(key)

            if not parameter_name:
                continue

            # Find matching parameter group in rolematrix_radio
            for group in rolematrix_radio:
                if group["parameter"] == parameter_name:

                    # Search the subsections inside the group
                    for sub in group["sub"]:
                        if sub["name"].strip().lower() == subsection.strip().lower():

                            # Only add if checker approval is TRUE
                            if sub.get("checker_approval"):

                                approval_req_radio.append({
                                    "parameter": parameter_name,
                                    "subsection": sub["name"],
                                    "checker_approval": "pending"
                                })
                    break
        approavl_dict = {}
        approavl_dict_field= {}
        approavl_dict_radio= {}
        if approval_req_field or approval_req_radio:
            if approval_req_field:
                original_data = invoice.original_data
                
                for key in approval_req_field:
                    app_dict = {}
                    app_dict['Original_Value'] = original_data.get(key,{}).get('original')
                    app_dict['Updated_Value'] = original_data.get(key,{}).get('updated')
                    app_dict['Checker_Approavl'] = 'pending'
                    approavl_dict_field[key] = app_dict

            if approval_req_radio:
                print(approval_req_radio)
                for element in approval_req_radio:
                    app_dict = {}
                    para = element['parameter']
                    section = element['subsection']
                    
                    app_dict['Section'] = section
                    app_dict['Original_Value'] = 'Red'
                    app_dict['Updated_Value'] = 'Yellow'
                    app_dict['Checker_Approavl'] = 'pending'
                    approavl_dict_radio[f"{para}"] = app_dict
            
            approavl_dict['approval_req_field'] = approavl_dict_field or {}
            approavl_dict['approval_req_radio'] = approavl_dict_radio or {}
            # print(approavl_dict)
            invoice.checker_approval = approavl_dict
            invoice.Pending_with = 'Checker'
            invoice.save()
            return JsonResponse({
                "status": "success",
                "message": "Invoice Approved and and Pending for Checker Approavl",
                "InvoiceGroupKey": invoice_key
            })
        else:
            invoice.Status = 'ready'
            invoice.save()

            return JsonResponse({
                "status": "success",
                "message": "Invoice Approved and moved to Ready status",
                "InvoiceGroupKey": invoice_key
            })

    else:
        print(role)
        invoice.Status = 'ready'
        invoice.save()

        return JsonResponse({
            "status": "success",
            "message": "Invoice Approved and moved to Ready status",
            "InvoiceGroupKey": invoice_key
        })

def reject_invoice(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)

    data = json.loads(request.body)
    invoice_key = data.get("invoice_group_key")

    print("Received InvoiceGroupKey:", invoice_key)

    try:
        invoice = InvoiceSummary.objects.get(InvoiceGroupKey=invoice_key)
    except InvoiceSummary.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Invoice not found"
        }, status=404)

    # ✅ Update fields
    invoice.Status = "rejected"
    invoice.save()

    return JsonResponse({
        "status": "success",
        "message": "Invoice Rejected and moved to Reejected status",
        "InvoiceGroupKey": invoice_key
    })

def hold_invoice(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)

    data = json.loads(request.body)
    invoice_key = data.get("invoice_group_key")

    print("Received InvoiceGroupKey:", invoice_key)

    try:
        invoice = InvoiceSummary.objects.get(InvoiceGroupKey=invoice_key)
    except InvoiceSummary.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": "Invoice not found"
        }, status=404)

    # ✅ Update fields
    invoice.Status = "rejected"
    invoice.save()

    return JsonResponse({
        "status": "success",
        "message": "Invoice Rejected and moved to Reejected status",
        "InvoiceGroupKey": invoice_key
    })

@csrf_exempt
def checker_edits_approve(request):

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)

    data = json.loads(request.body)
    invoice_key = data.get("invoice_group_key")
    parameter = data.get("parameter")
    type_ = data.get("type")
    sub = data.get("sub")
    matrix = data.get("matrix")
    print(data)
    invoice = InvoiceSummary.objects.get(InvoiceGroupKey=invoice_key)
    approval_json = invoice.checker_approval
    print(approval_json)
    try:
        if type_ == 'single':
            if matrix == "Radio Matrix":
                # Update nested JSON:
                for key,value in approval_json['approval_req_radio'].items():
                    if key == parameter and value['param'] == sub:
                        data["Checker_Approavl"] = "Approved"            
            else:
                for key,value in approval_json['approval_req_field'].items():
                    if key == parameter:
                        value["Checker_Approavl"] = "Approved" 
            invoice.checker_approval = approval_json
            invoice.save()
            return JsonResponse({"status": "ok", "message": f"{parameter} approved"})
        else:
            # Update nested JSON:
            for key,value in approval_json.items():
                if value:
                    for key1,value1 in value.items():
                        value1["Checker_Approavl"] = "Approved"
            invoice.checker_approval = approval_json
            invoice.save()
            return JsonResponse({"status": "ok", "message": f"{parameter} approved"})
    except Exception as e:
        print("Error :",e, traceback.format_exc())
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=400)
    
@csrf_exempt
def resubmit_nodata_invoice(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    try:
        data = json.loads(request.body)
        company = request.user.company_code  # already available in your session
        invoice_group_key = data.get("invoice_group_key")
        vendor_code = data.get("VendorCode")
        invoice_no = data.get("invoice_no")
        updated_gst = data.get("updatedGSTNo")
        tab = data.get("tab")

        # 🔍 Debug output
        print("----- Resubmit No-Data Invoice -----")
        print("Invoice Group Key:", invoice_group_key)
        print("Invoice No:", invoice_no)
        print("Vendor Code:", vendor_code)
        print("Updated GST:", updated_gst)
        print("Tab:", tab)
        print("----------------------------------")
        unique_record = MissingDataInvoices.objects.get(InvoiceGroupKey=invoice_group_key)
        unique_name = unique_record.unique_name
        invoice_path = unique_record.path
        api_response = unique_record.api_response
        if unique_record.VendorGst == updated_gst:
            save_processed_invoice(api_response,invoice_path, unique_name, company, invoice_group_key)
        else:
            try:
                url = "https://ngtechocr.azurewebsites.net/process-invoice-withchecks-updated-splitting"
                App = 'WFS'
                invoice_data = api_response.get('result', {}).get('Invoice_data', {})
                data = {
                    'user_id': 'miroapp',
                    'password': '0000@Maa',
                    'App': App,
                    'ocr': 'false',
                    'datadict': json.dumps(invoice_data)
                }
                response = requests.post(url, data=data)
                if response.status_code == 200:
                    process_incoming_file(api_response,company,invoice_path,unique_name,invoice_group_key)
            except Exception as e:
                print("Error :",e, traceback.format_exc())
        return JsonResponse({
            "success": True,
            "message": "Payload received successfully",
            "payload": data
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": str(e)
        })


