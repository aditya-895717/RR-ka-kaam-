from django.urls import path

from . import views

urlpatterns = [
    # Hospital
    path('invoices/',                                    views.InvoiceListView.as_view(),          name='billing_invoice_list'),
    path('invoices/<uuid:invoice_id>/',                  views.InvoiceDetailView.as_view(),         name='billing_invoice_detail'),
    # Laundry
    path('laundry/invoices/',                            views.LaundryInvoiceListView.as_view(),    name='billing_laundry_invoice_list'),
    path('laundry/invoices/<uuid:invoice_id>/',          views.LaundryInvoiceDetailView.as_view(),  name='billing_laundry_invoice_detail'),
    path('laundry/invoices/<uuid:invoice_id>/mark-paid/', views.MarkPaidView.as_view(),             name='billing_mark_paid'),
]
