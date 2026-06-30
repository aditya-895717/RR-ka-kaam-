from django import forms

from accounts.models import HospitalDepartment
from .models import ItemType, OrderStatus

_TEXT   = {'class': 'form-control'}
_SELECT = {'class': 'form-select'}
_SM     = {'class': 'form-control form-control-sm'}
_SM_SEL = {'class': 'form-select form-select-sm'}


class DepartmentForm(forms.Form):
    department_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={**_TEXT, 'placeholder': 'e.g. ICU, Orthopaedics'}),
    )


class NewOrderForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=HospitalDepartment.objects.none(),
        label='Department',
        empty_label='— Select department —',
        widget=forms.Select(attrs=_SELECT),
    )

    def __init__(self, hospital, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = HospitalDepartment.objects.filter(
            hospital=hospital,
        )


class OrderFilterForm(forms.Form):
    STATUS_ALL = [('', 'All Statuses')]

    status = forms.ChoiceField(
        choices=STATUS_ALL + list(OrderStatus.choices),
        required=False,
        widget=forms.Select(attrs=_SM_SEL),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**_SM, 'type': 'date'}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**_SM, 'type': 'date'}),
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={**_SM, 'placeholder': 'Search order ID…'}),
    )
