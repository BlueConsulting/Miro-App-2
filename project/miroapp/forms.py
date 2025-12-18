from django import forms
from .models import CompanyDetails

class CompanyDetailsForm(forms.ModelForm):
    class Meta:
        model = CompanyDetails
        fields = ['business_name', 'business_code', 'constitution', 'contact_person_name', 
                  'country_code', 'contact_person_number', 'contact_person_email', 
                  'address_line1', 'address_line2']

    def clean_contact_person_email(self):
        email = self.cleaned_data['contact_person_email']
        if CompanyDetails.objects.filter(contact_person_email=email).exists():
            raise forms.ValidationError("Email is already registered.")
        return email