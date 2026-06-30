from rest_framework import serializers

from .models import Invoice, InvoiceLineItem


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    department_name = serializers.SerializerMethodField()

    class Meta:
        model  = InvoiceLineItem
        fields = ['id', 'department_name', 'item_count', 'price_per_item', 'line_total']

    def get_department_name(self, obj):
        return obj.department.department_name if obj.department else 'Unassigned'


class InvoiceSerializer(serializers.ModelSerializer):
    hospital_name        = serializers.CharField(source='hospital.hospital_name', read_only=True)
    laundry_partner_name = serializers.SerializerMethodField()
    order_short_id       = serializers.CharField(source='order.short_id', read_only=True)
    line_items           = InvoiceLineItemSerializer(many=True, read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            'invoice_id', 'invoice_number', 'order_short_id',
            'hospital_name', 'laundry_partner_name',
            'price_per_item', 'total_items', 'total_amount',
            'status', 'generated_at', 'paid_at', 'due_date',
            'line_items',
        ]

    def get_laundry_partner_name(self, obj):
        return obj.laundry_partner.business_name if obj.laundry_partner else '—'
