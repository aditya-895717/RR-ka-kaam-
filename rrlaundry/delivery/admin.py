from django.contrib import admin

from .models import DeliveryJob


@admin.register(DeliveryJob)
class DeliveryJobAdmin(admin.ModelAdmin):
    list_display  = ('short_id', 'order', 'delivery_partner', 'job_type', 'status', 'assigned_at', 'completed_at')
    list_filter   = ('job_type', 'status')
    search_fields = ('order__order_id', 'delivery_partner__company_name')
    readonly_fields = ('job_id', 'assigned_at', 'started_at', 'completed_at')

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == 'COMPLETED':
            return False
        return super().has_delete_permission(request, obj)
