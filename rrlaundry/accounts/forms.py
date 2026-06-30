from django import forms

from .models import Role, HospitalProfile, HospitalDepartment, LaundryProfile

_TEXT = {'class': 'form-control'}
_SELECT = {'class': 'form-select'}
_TEXTAREA = {'class': 'form-control', 'rows': 3}
_NUMBER = {'class': 'form-control', 'step': '0.01', 'min': '0'}


class RoleSelectionForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices, widget=forms.HiddenInput())


class HospitalHeadOnboardingForm(forms.Form):
    hospital_name = forms.CharField(
        max_length=255, label='Hospital Name',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. BHU Hospital'}),
    )
    hospital_address = forms.CharField(
        label='Full Address',
        widget=forms.Textarea(attrs={**_TEXTAREA, 'placeholder': 'Street, locality, landmark…'}),
    )
    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Varanasi'}),
    )
    area = forms.CharField(
        max_length=100, label='Area / Locality',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Lanka, BHU Campus'}),
    )
    phone_number = forms.CharField(
        max_length=20, label='Contact Phone',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': '+91 XXXXX XXXXX'}),
    )


class HospitalStaffOnboardingForm(forms.Form):
    hospital = forms.ModelChoiceField(
        queryset=HospitalProfile.objects.all(),
        label='Your Hospital',
        empty_label='— Select a registered hospital —',
        widget=forms.Select(attrs=_SELECT),
        help_text='If your hospital is not listed, ask your Hospital Head to register first.',
    )
    department = forms.ModelChoiceField(
        queryset=HospitalDepartment.objects.all(),
        label='Department',
        required=False,
        empty_label='— No specific department —',
        widget=forms.Select(attrs=_SELECT),
    )
    phone_number = forms.CharField(
        max_length=20, label='Your Phone Number',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': '+91 XXXXX XXXXX'}),
    )


class LaundryAdminOnboardingForm(forms.Form):
    business_name = forms.CharField(
        max_length=255, label='Business / Shop Name',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Dubey Laundry Services'}),
    )
    address = forms.CharField(
        label='Full Address',
        widget=forms.Textarea(attrs={**_TEXTAREA, 'placeholder': 'Street, locality, landmark…'}),
    )
    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Varanasi'}),
    )
    area = forms.CharField(
        max_length=100, label='Area / Locality',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Sigra, Assi'}),
    )
    phone_number = forms.CharField(
        max_length=20, label='Contact Phone',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': '+91 XXXXX XXXXX'}),
    )
    price_per_item = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=0,
        label='Base Price per Item (₹)',
        initial='0.00',
        widget=forms.NumberInput(attrs={**_NUMBER, 'placeholder': '0.00'}),
    )


class LaundryWorkerOnboardingForm(forms.Form):
    laundry = forms.ModelChoiceField(
        queryset=LaundryProfile.objects.all(),
        label='Your Laundry Shop',
        empty_label='— Select a registered laundry —',
        widget=forms.Select(attrs=_SELECT),
        help_text='If your shop is not listed, ask your Laundry Admin to register first.',
    )
    phone_number = forms.CharField(
        max_length=20, label='Your Phone Number',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': '+91 XXXXX XXXXX'}),
    )


class DeliveryPartnerOnboardingForm(forms.Form):
    VEHICLE_CHOICES = [
        ('', '— Select vehicle type (optional) —'),
        ('BIKE', 'Bike'),
        ('AUTO', 'Auto'),
        ('VAN', 'Van'),
        ('OTHER', 'Other'),
    ]

    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Varanasi'}),
    )
    area = forms.CharField(
        max_length=100, label='Area / Locality',
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. Lanka, Godowlia'}),
    )
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': '+91 XXXXX XXXXX'}),
    )
    vehicle_type = forms.ChoiceField(
        choices=VEHICLE_CHOICES,
        required=False,
        label='Vehicle Type',
        widget=forms.Select(attrs=_SELECT),
    )
