from django.contrib import admin

from .models import Invoice, InvoiceLineItem


class InvoiceLineItemInline(admin.TabularInline):
    model  = InvoiceLineItem
    extra  = 0
    fields = ('department', 'item_count', 'price_per_item', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display   = ('invoice_number', 'hospital', 'laundry_partner', 'total_items',
                      'total_amount', 'status', 'generated_at', 'due_date')
    list_filter    = ('status',)
    search_fields  = ('invoice_number', 'hospital__hospital_name')
    readonly_fields = ('invoice_id', 'invoice_number', 'generated_at')
    inlines        = [InvoiceLineItemInline]


@admin.register(InvoiceLineItem)
class InvoiceLineItemAdmin(admin.ModelAdmin):
    list_display  = ('invoice', 'department', 'item_count', 'price_per_item', 'line_total')
    list_select_related = ('invoice', 'department')
