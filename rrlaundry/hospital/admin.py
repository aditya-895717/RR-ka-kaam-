from django.contrib import admin
from .models import HospitalPartnerSelection, LaundryOrder, OrderItem


@admin.register(HospitalPartnerSelection)
class HospitalPartnerSelectionAdmin(admin.ModelAdmin):
    list_display  = ['hospital', 'laundry_partner', 'delivery_partner', 'is_active', 'selected_at']
    list_filter   = ['is_active']
    raw_id_fields = ['hospital', 'laundry_partner', 'delivery_partner']


class OrderItemInline(admin.TabularInline):
    model  = OrderItem
    extra  = 0
    fields = ['tag_number', 'item_type', 'current_status', 'department']


@admin.register(LaundryOrder)
class LaundryOrderAdmin(admin.ModelAdmin):
    list_display   = ['short_id', 'hospital', 'department', 'status', 'created_at', 'created_by']
    list_filter    = ['status']
    search_fields  = ['order_id', 'hospital__hospital_name']
    inlines        = [OrderItemInline]
    readonly_fields = ['order_id', 'created_at', 'updated_at']
    raw_id_fields  = ['hospital', 'laundry_partner', 'delivery_partner', 'department', 'created_by']


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display  = ['tag_number', 'item_type', 'current_status', 'order', 'added_at']
    list_filter   = ['item_type', 'current_status']
    search_fields = ['tag_number']
    raw_id_fields = ['order', 'department']
