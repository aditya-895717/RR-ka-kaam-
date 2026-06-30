from django import forms

from .models import FloorStage


class PricingForm(forms.Form):
    price_per_item = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={
            'step': '0.50',
            'style': 'max-width: 200px;',
        }),
        label='Price per Item (₹)',
    )


class StageUpdateForm(forms.Form):
    tag_number = forms.CharField(max_length=50)
    new_stage  = forms.ChoiceField(choices=FloorStage.choices)
    worker_id  = forms.UUIDField(required=False)
    notes      = forms.CharField(required=False, max_length=500)


class WorkerAssignForm(forms.Form):
    tag_number = forms.CharField(max_length=50)
    worker_id  = forms.UUIDField()
