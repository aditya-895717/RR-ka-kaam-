from django.contrib import admin

from .models import DashboardNotification


@admin.register(DashboardNotification)
class DashboardNotificationAdmin(admin.ModelAdmin):
    list_display  = ['recipient', 'title', 'tag_number', 'notification_type', 'is_read', 'created_at']
    list_filter   = ['notification_type', 'is_read']
    search_fields = ['tag_number', 'recipient__email', 'title']
    readonly_fields = ['created_at']
    ordering      = ['-created_at']
    actions       = ['mark_read']

    @admin.action(description='Mark selected as read')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)
