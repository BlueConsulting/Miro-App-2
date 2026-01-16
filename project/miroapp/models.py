from django.utils import timezone
from django.db import models
from django.db import connection
# Create your models here.
# models.py


from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    company_code = models.ForeignKey(
        'CompanyDetails',  # Reference to your company model
        on_delete=models.CASCADE,
        related_name='users'
    )
    role = models.CharField(max_length=20)  # Role (e.g., Admin, Manager, Employee)
    
    status = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"
    

    
class CompanyDetails(models.Model):
    business_name = models.CharField(max_length=255)
    business_code = models.CharField(max_length=50)
    constitution = models.CharField(
        max_length=50,
        choices=[
            ('Public Ltd', 'Public Ltd'),
            ('Private Ltd', 'Private Ltd'),
            ('LLP', 'LLP'),
            ('Proprietorship', 'Proprietorship'),
            ('Partnership', 'Partnership'),
            ('Trust', 'Trust')
        ]
    )
    contact_person_name = models.CharField(max_length=255)
    country_code = models.CharField(
        max_length=10,
        choices=[
            ('+91', 'India (+91)'),
            ('+1', 'USA (+1)'),
            ('+44', 'UK (+44)'),
            ('+61', 'Australia (+61)'),
            ('+81', 'Japan (+81)'),
        ]
        )
    contact_person_number = models.CharField(max_length=20)
    contact_person_email = models.EmailField(unique=True)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=128, blank=True, null=True)  # Will be updated after user sets password
    company_code = models.AutoField(primary_key=True)  # Auto-incremented unique code for the company
    last_login = models.DateTimeField(null=True, blank=True)  # Add this field

    
    def __str__(self):
        return f"{self.business_name} ({self.contact_person_email})"
    
class InvoiceDetail(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=255, unique=True)  # Unique constraint
    path = models.TextField()
    upload_date = models.TextField(blank=True, null=True)
    okay_status = models.TextField(blank=True, null=True)
    okay_message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, default='waiting')
    
class Header(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    # Store headers as a list of strings sac_master_headers
    po_header = models.JSONField(default=list, help_text="List of expected PO headers")
    miro_header = models.JSONField(default=list, help_text="List of expected MIRO headers")
    se_header = models.JSONField(default=list, help_text="List of expected Service entry headers")
    system_var= models.JSONField(default=list, help_text="List of system variables")
    vendor_master_header = models.JSONField(default=list, help_text="Vendor master headers")
    item_master_header = models.JSONField(default=list, help_text="Item master headers")
    sac_master_headers = models.JSONField(default=list, help_text="SAC master headers")
    wholdtax_master_headers = models.JSONField(default=list, help_text="SAC master headers")
    gsttax_master_headers = models.JSONField(default=list, help_text="GST master headers")
    hsn_master_headers = models.JSONField(default=list, help_text="HSN master headers")
    unalloacatedcost_gl = models.JSONField(default=list, help_text="list of gl for unallocated cost")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Headers for User: {self.company}"
    
class SystemVariableMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    # Store headers as a list of strings sac_master_headers
    system_var = models.CharField(max_length=50) 
    po_header= models.CharField(max_length=50)
    miro_header = models.CharField(max_length=50)
    se_header = models.CharField(max_length=50)
    secondary_source = models.CharField(max_length=50)
    
    
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"SystemVariableMapping for User: {self.company}"
    
class AdditionalSystemVariableMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    # Store headers as a list of strings sac_master_headers
    system_var = models.CharField(max_length=50) 
    system_var_user_name = models.CharField(max_length=50) 
    po_header= models.CharField(max_length=50)
    miro_header = models.CharField(max_length=50)
    se_header = models.CharField(max_length=50)
    
    
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"SystemVariableMapping for User: {self.company}"
    

    
class OpenGRNData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    vendor_code = models.CharField(max_length=16) 
    document_number = models.CharField(max_length=20) 
    inv_no = models.CharField(max_length=40)
    row_data = models.JSONField()                   # stores entire row as JSON
    status = models.CharField(max_length=16)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "open_grn_data"
        indexes = [
            models.Index(fields=["vendor_code"]),
        ]
        verbose_name = "Open GRN Data"
        verbose_name_plural = "Open GRN Data"

    def __str__(self):
        return f"{self.vendor_code}"
    
class POData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    vendor_code = models.CharField(max_length=16)
    document_number = models.CharField(max_length=20) 
    inv_no = models.CharField(max_length=40)  
    row_data = models.JSONField()                   # stores entire row as JSON
    status = models.CharField(max_length=16)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "po_data"
        indexes = [
            models.Index(fields=["vendor_code"]),
        ]
        verbose_name = "PO Data"
        verbose_name_plural = "PO Data"

    def __str__(self):
        return f"{self.vendor_code}"
    
class SECData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    vendor_code = models.CharField(max_length=16)
    document_number = models.CharField(max_length=20)   
    row_data = models.JSONField()                   # stores entire row as JSON
    status = models.CharField(max_length=16)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sec_data"
        indexes = [
            models.Index(fields=["vendor_code"]),
        ]
        verbose_name = "SEC Data"
        verbose_name_plural = "SEC Data"

    def __str__(self):
        return f"{self.vendor_code}"
    
class OcrOutput(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE)

    vendor_code = models.CharField(max_length=16)
    vendor_name = models.CharField(max_length=20)
    gst_number = models.CharField(max_length=100)
    invoice_record = models.CharField(max_length=16)   
    row_data = models.JSONField()                   # stores entire data from ocr as JSON
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "OcrOutput"
        indexes = [
            models.Index(fields=["invoice_record"]),
        ]
        verbose_name = "OcrOutput Data"
        verbose_name_plural = "OcrOutput Data"

    def __str__(self):
        return f"{self.vendor_code}"
    
class VendorMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="vendor_mappings")

    VendorName = models.CharField(max_length=50, blank=True, null=True)
    VendorCode = models.CharField(max_length=50, blank=True, null=True)
    GSTNo = models.CharField(max_length=50, blank=True, null=True)
    LDCNo = models.CharField(max_length=50, blank=True, null=True)
    LDCThreshold = models.CharField(max_length=50, blank=True, null=True)
    LDCStartDate = models.CharField(max_length=50, blank=True, null=True)
    LDCEndDate = models.CharField(max_length=50, blank=True, null=True)
    LDCWTCode = models.CharField(max_length=50, blank=True, null=True)
    BlockedYN = models.CharField(max_length=50, blank=True, null=True)
    MSMERegisteredYN = models.CharField(max_length=50, blank=True, null=True)
    MSMENumber = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Vendor Master Mapping - {self.company}"
    
class VendorMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="vendor_master_data")

    VendorName = models.CharField(max_length=100, blank=True, null=True)
    VendorCode = models.CharField(max_length=15, blank=True, null=True)
    GSTNo = models.CharField(max_length=16, blank=True, null=True)
    LDCNo = models.CharField(max_length=15, blank=True, null=True)
    LDCThreshold = models.CharField(max_length=15, blank=True, null=True)
    LDCStartDate = models.CharField(max_length=12, blank=True, null=True)
    LDCEndDate = models.CharField(max_length=12, blank=True, null=True)
    LDCWTCode = models.CharField(max_length=3, blank=True, null=True)
    BlockedYN = models.CharField(max_length=5, blank=True, null=True)
    MSMERegisteredYN = models.CharField(max_length=5, blank=True, null=True)
    MSMENumber = models.CharField(max_length=15, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Vendor Master Data - {self.company}"
    
class ItemMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="item_mappings")

    ItemNumber = models.CharField(max_length=50, blank=True, null=True)
    ItemDescription = models.CharField(max_length=50, blank=True, null=True)
    HSNCode = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Item Master Mapping - {self.company}"

class ItemMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="item_master_data")

    ItemNumber = models.CharField(max_length=15, blank=True, null=True)
    ItemDescription = models.CharField(max_length=250, blank=True, null=True)
    HSNCode = models.CharField(max_length=10, blank=True, null=True)    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Item Master Data - {self.company}"
    
class SACMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="sac_mappings")

    saccode = models.CharField(max_length=50, blank=True, null=True)
    sacDescription = models.CharField(max_length=50, blank=True, null=True)
    taxrate = models.CharField(max_length=50, blank=True, null=True)
    block_input = models.CharField(max_length=50, blank=True, null=True)
    rcm_fc = models.CharField(max_length=50, blank=True, null=True) 
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SAC Master Mapping - {self.company}"
    
class SACMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="sac_master_data")

    saccode = models.CharField(max_length=10, blank=True, null=True)
    sacDescription = models.CharField(max_length=250, blank=True, null=True)
    taxrate = models.CharField(max_length=2, blank=True, null=True)
    block_input = models.CharField(max_length=10, blank=True, null=True)
    rcm_fc = models.CharField(max_length=15, blank=True, null=True)    
    section = models.CharField(max_length=5, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SAC Master Data - {self.company}"
    
class HsnMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="hsn_mappings")

    hsncode = models.CharField(max_length=15, blank=True, null=True)
    hsnDescription = models.CharField(max_length=50, blank=True, null=True)
    cgstrate = models.CharField(max_length=2, blank=True, null=True)
    sgstrate = models.CharField(max_length=2, blank=True, null=True)
    igstrate = models.CharField(max_length=2, blank=True, null=True)
    block_input = models.CharField(max_length=10, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"HSN Master Mapping - {self.company}"
    
class HsnMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="hsn_master_data")

    hsncode = models.CharField(max_length=15, blank=True, null=True)
    hsnDescription = models.CharField(max_length=250, blank=True, null=True)
    cgstrate = models.CharField(max_length=3, blank=True, null=True)
    sgstrate = models.CharField(max_length=3, blank=True, null=True)
    igstrate = models.CharField(max_length=3, blank=True, null=True)
    block_input = models.CharField(max_length=5, blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"HSN Master Data - {self.company}"
    
class withholdingtaxMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="withholdingtax_mappings")

    wtaxcode = models.CharField(max_length=50, blank=True, null=True)
    wtaxcoderate = models.CharField(max_length=50, blank=True, null=True)
    ldc = models.CharField(max_length=50, blank=True, null=True)
    ldtrate = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WithHoldingRate Master Mapping - {self.company}"
    
class withholdingtaxMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="withholdingtax_master_data")

    wtaxcode = models.CharField(max_length=30, blank=True, null=True)
    wtaxsection = models.CharField(max_length=30, blank=True, null=True)
    wtaxcoderate = models.CharField(max_length=5, blank=True, null=True)
    ldc = models.CharField(max_length=5, blank=True, null=True)
    ldtrate = models.CharField(max_length=5, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WithHoldingRate Master Data - {self.company}"
    
class gsttaxMastersMapping(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="gsttax_mappings")

    gsttaxcode = models.CharField(max_length=50, blank=True, null=True)
    cgstrate = models.CharField(max_length=50, blank=True, null=True)
    sgstrate = models.CharField(max_length=50, blank=True, null=True)
    igstrate = models.CharField(max_length=50, blank=True, null=True)
    bc_ic = models.CharField(max_length=50, blank=True, null=True)
    fc_rc = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GSTTaxrate Master Mapping - {self.company}"
    
class gsttaxMastersData(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="gsttax_master_data")

    gsttaxcode = models.CharField(max_length=5, blank=True, null=True)
    cgstrate = models.CharField(max_length=3, blank=True, null=True)
    sgstrate = models.CharField(max_length=3, blank=True, null=True)
    igstrate = models.CharField(max_length=3, blank=True, null=True)
    bc_ic = models.CharField(max_length=5, blank=True, null=True)
    fc_rc = models.CharField(max_length=5, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GSTTaxRate Master Data - {self.company}"
    
class VendorsTotals(models.Model):
    company = models.ForeignKey(CompanyDetails, on_delete=models.CASCADE, related_name="vendor_invoice_total")

    Vendor_code = models.CharField(max_length=11, blank=True, null=True)
    inv_num = models.CharField(max_length=20, blank=True, null=True)
    inv_date = models.DateField(blank=True, null=True)
    inv_value = models.FloatField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Vendors Total Data - {self.Vendor_code}"
    
class Configurations(models.Model):
    company = models.ForeignKey(
        CompanyDetails,
        on_delete=models.CASCADE,
        related_name="configurations"
    )

    monthly_close = models.JSONField(default=dict)
    baseline = models.JSONField(default=dict)
    blocking = models.JSONField(default=dict)
    matching = models.JSONField(default=dict)
    currency = models.JSONField(default=dict)
    narration = models.JSONField(default=dict)
    duplicate_check = models.JSONField(default=dict)
    unplanned_cost = models.JSONField(default=dict)
    threshold = models.JSONField(default=dict)
    service_entry_migo = models.JSONField(default=dict)
    matching_logic_ratio = models.JSONField(default=dict)
    data_upload_rights = models.JSONField(default=dict)
    pans = models.CharField(max_length=10, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuration for {self.company}"
    
class addsystemvariable(models.Model):
    company = models.ForeignKey(
        CompanyDetails,
        on_delete=models.CASCADE,
        related_name="addsystemname"
    )
    variable1 = models.JSONField(default=dict)
    variable2 = models.JSONField(default=dict)
    variable3 = models.JSONField(default=dict)
    variable4 = models.JSONField(default=dict)
    variable5 = models.JSONField(default=dict)
    variable6 = models.JSONField(default=dict)
    variable7 = models.JSONField(default=dict)
    variable8 = models.JSONField(default=dict)
    variable9 = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuration for {self.company}"
    

import uuid

class InvoiceDetails(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    invoice_key = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)  # 🔑 unique per invoice

    InvoiceId = models.PositiveIntegerField(db_index=True)
    CompanyCode = models.CharField(max_length=10)
    DocumentNumber = models.CharField(max_length=15)
    DocType = models.CharField(max_length=5)
    InvoiceDate = models.CharField(max_length=11)
    PostingDate = models.CharField(max_length=11)
    AP_Inv_doc_num = models.CharField(max_length=50)
    Currency = models.CharField(max_length=5)
    ExchangeRate = models.CharField(max_length=3)
    VendorCode = models.CharField(max_length=15)
    VendorName = models.CharField(max_length=100)
    PaymentTerms = models.CharField(max_length=5)
    BaselineDate = models.CharField(max_length=11)
    PO_Number = models.CharField(max_length=15)
    PO_Item = models.CharField(max_length=15)
    GR_Number = models.CharField(max_length=15)
    MaterialNo = models.CharField(max_length=15)
    Qty_Invoiced = models.CharField(max_length=4)
    UoM = models.CharField(max_length=4)
    NetPrice = models.CharField(max_length=15)
    InvoiceAmount = models.CharField(max_length=20)
    TaxCode = models.CharField(max_length=5)
    TaxAmount = models.CharField(max_length=15)
    WithholdingTaxCode = models.CharField(max_length=5)
    UnplannedDeliveryCost = models.CharField(max_length=15)
    GLAccount = models.CharField(max_length=15)
    CostCenter = models.CharField(max_length=10)
    WBS_Element = models.CharField(max_length=50)
    AssetNo = models.CharField(max_length=15)
    PaymentBlock = models.CharField(max_length=5)
    Narration = models.CharField(max_length=50)
    MigoDocDate = models.CharField(max_length=11)
    SuppInv_no = models.CharField(max_length=30)
    item_rate = models.CharField(max_length=30)
    item_descritption = models.CharField(max_length=50) 

    def __str__(self):
        return f"{self.VendorCode} - {self.SuppInv_no}"
    
class InvoiceSummary(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    InvoiceGroupKey = models.UUIDField(db_index=True)  # links to InvoiceDetails.InvoiceGroupKey

    InvoiceId = models.PositiveIntegerField(db_index=True)
    path = models.TextField()
    unique_name = models.CharField(max_length=100, blank=True, null=True)
    VendorCode = models.CharField(max_length=15, blank=True, null=True)
    VendorName = models.CharField(max_length=100, blank=True, null=True)
    InvoiceNo = models.CharField(max_length=50, blank=True, null=True)
    InvoiceDate = models.DateField(blank=True, null=True)
    VendorGst = models.CharField(max_length=15, blank=True, null=True)
    InvoiceValue = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    InvoiceValueMigo = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    ExchangeRate = models.CharField(max_length=3, blank=True, null=True)
    TaxCode = models.CharField(max_length=30, blank=True, null=True)
    WithholdingTaxCode = models.CharField(max_length=30, blank=True, null=True)
    Narration = models.CharField(max_length=50, blank=True, null=True)
    InvoiceCheck = models.JSONField(default=dict)
    Status = models.CharField(max_length=20, blank=True, null=True, default='Pending')
    Pending_with = models.CharField(max_length=20, default='Processor')
    original_data = models.JSONField(default=dict)
    checker_approval = models.JSONField(default=dict)
    field_matrix_change = models.JSONField(default=list)
    radio_matrix_change = models.JSONField(default=list)
    payment_indicator = models.CharField(max_length=10, blank=True, null=True)
    Currency = models.CharField(max_length=5, blank=True, null=True)
    InvCurrency = models.CharField(max_length=5, blank=True, null=True)
    account_indicator = models.CharField(max_length=3, blank=True, null=True)
    withholdtax = models.CharField(max_length=10, blank=True, null=True)
    CreatedAt = models.DateTimeField(auto_now_add=True)
    unplanned_cost = models.JSONField(default=dict)
    UpdatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.VendorName} | {self.InvoiceNo} | {self.InvoiceValue}"

    class Meta:
        verbose_name_plural = "Invoice Summaries"
        ordering = ['-CreatedAt']

class TemplateMapping(models.Model):
    company_code = models.CharField(max_length=100)
    mapped_headers1 = models.JSONField(default=dict)
    mapped_headers2 = models.JSONField(default=dict)
    file_no = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Template Mapping for {self.company_code}"
    
class PendingInvoices(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    InvoiceGroupKey = models.UUIDField(db_index=True)  # links to InvoiceDetails.InvoiceGroupKey

    InvoiceId = models.PositiveIntegerField(db_index=True)
    VendorGst = models.CharField(max_length=16)
    VendorCode = models.CharField(max_length=16)
    InvNo = models.CharField(max_length=16)
    InvDate = models.CharField(max_length=16)
    VendorName = models.CharField(max_length=50)
    CustomerGst = models.CharField(max_length=16)
    TotalAmount = models.CharField(max_length=16)
    TotalTax = models.CharField(max_length=16)
    BasicAmount = models.CharField(max_length=16)
    TaxType = models.JSONField(default=dict)
    path = models.TextField()
    unique_name = models.CharField(max_length=100, blank=True, null=True)
    api_response = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Template Mapping for {self.company}"
    
class MissingDataInvoices(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    InvoiceGroupKey = models.UUIDField(db_index=True)  # links to InvoiceDetails.InvoiceGroupKey

    InvoiceId = models.PositiveIntegerField(db_index=True)
    VendorGst = models.CharField(max_length=16)
    VendorCode = models.CharField(max_length=16, blank=True, null=True)
    InvNo = models.CharField(max_length=30, blank=True, null=True)
    InvDate = models.CharField(max_length=16)
    InvoiceCheck = models.JSONField(default=dict)
    VendorName = models.CharField(max_length=50)
    CustomerGst = models.CharField(max_length=16)
    TotalAmount = models.CharField(max_length=16)
    TotalTax = models.CharField(max_length=16) 
    BasicAmount = models.CharField(max_length=16)
    TaxType = models.JSONField(default=dict)
    path = models.TextField()
    unique_name = models.CharField(max_length=100, blank=True, null=True)
    message = models.CharField(max_length=150, blank=True, null=True)
    api_response = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='Pending')
    checker_approval = models.JSONField(default=dict)
    checker_approval_req = models.CharField(max_length=4, default='No')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Template Mapping for {self.company}"

class CheckerApprovalsInvoices(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    InvoiceGroupKey = models.UUIDField(db_index=True)  # links to InvoiceDetails.InvoiceGroupKey

    InvoiceId = models.PositiveIntegerField(db_index=True)
    VendorCode=models.CharField(max_length=16, blank=True, null=True)
    VendorName=models.CharField(max_length=50)
    InvoiceNo=models.CharField(max_length=30, blank=True, null=True)
    path = models.TextField()
    unique_name = models.CharField(max_length=100, blank=True, null=True)
    api_response = models.JSONField(default=dict)
    message = models.CharField(max_length=150, blank=True, null=True)
    exception_type = models.CharField(max_length=30, blank=True, null=True)
    exception_data = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='Pending')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Template Mapping for {self.company}"
    
class RoleMatrix(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)

    field_matrix = models.JSONField(default=dict)
    radio_matrix = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Role Matrix for {self.company}"
    
class GLCodes(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)

    gl_code = models.CharField(max_length=16) 
    code_description = models.CharField(max_length=50)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GL code for {self.company}"
    
class InvoiceId(models.Model):
    company = models.ForeignKey('CompanyDetails', on_delete=models.CASCADE)
    
    path = models.TextField()
    unique_name = models.CharField(max_length=100, blank=True, null=True)
    VendorName = models.CharField(max_length=100, blank=True, null=True)
    InvoiceNo = models.CharField(max_length=50, blank=True, null=True)
    InvoiceDate = models.DateField(blank=True, null=True)
    VendorGst = models.CharField(max_length=15, blank=True, null=True)
    
    
    UpdatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.VendorName} | {self.InvoiceNo} | {self.InvoiceValue}"
    

