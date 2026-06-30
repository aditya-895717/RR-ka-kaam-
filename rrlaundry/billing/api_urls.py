from django.urls import path

from . import api

urlpatterns = [
    path('invoices/',                            api.InvoiceListAPIView.as_view(),   name='api_billing_invoice_list'),
    path('invoices/<uuid:invoice_id>/',          api.InvoiceDetailAPIView.as_view(), name='api_billing_invoice_detail'),
    path('invoices/<uuid:invoice_id>/mark-paid/', api.MarkPaidAPIView.as_view(),     name='api_billing_mark_paid'),
]
