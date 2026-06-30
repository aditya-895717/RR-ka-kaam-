from django.contrib import admin

from .models import ReconciliationLog, RFIDScanEvent


@admin.register(RFIDScanEvent)
class RFIDScanEventAdmin(admin.ModelAdmin):
    list_display  = ['tag_number', 'scan_point', 'order', 'scanned_by', 'scanned_at', 'location_note']
    list_filter   = ['scan_point']
    search_fields = ['tag_number', 'order__order_id']
    readonly_fields = ['scan_id', 'scanned_at']
    ordering      = ['-scanned_at']


@admin.register(ReconciliationLog)
class ReconciliationLogAdmin(admin.ModelAdmin):
    list_display  = [
        'order', 'scan_point_from', 'scan_point_to',
        'expected_count', 'received_count', 'is_matched', 'logged_at',
    ]
    list_filter   = ['is_matched', 'scan_point_from', 'scan_point_to']
    search_fields = ['order__order_id']
    readonly_fields = ['logged_at']
    ordering      = ['-logged_at']
