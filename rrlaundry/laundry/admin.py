from django.contrib import admin

from .models import ItemStageLog, MissingItemAlert, WorkerItemAssignment


class ItemStageLogInline(admin.TabularInline):
    model = ItemStageLog
    extra = 0
    readonly_fields = ('updated_at',)


@admin.register(ItemStageLog)
class ItemStageLogAdmin(admin.ModelAdmin):
    list_display = ('order_item', 'stage', 'updated_by', 'updated_at')
    list_filter  = ('stage',)
    search_fields = ('order_item__tag_number',)
    readonly_fields = ('updated_at',)


class WorkerItemAssignmentAdmin(admin.ModelAdmin):
    list_display = ('order_item', 'worker', 'is_first_worker', 'assigned_at')
    list_filter  = ('is_first_worker',)
    search_fields = ('order_item__tag_number',)
    readonly_fields = ('assigned_at',)

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_first_worker:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_first_worker:
            return False
        return super().has_delete_permission(request, obj)


admin.site.register(WorkerItemAssignment, WorkerItemAssignmentAdmin)


@admin.register(MissingItemAlert)
class MissingItemAlertAdmin(admin.ModelAdmin):
    list_display  = ('order_item', 'last_stage', 'triggered_at', 'is_resolved', 'resolved_at')
    list_filter   = ('is_resolved', 'last_stage')
    search_fields = ('order_item__tag_number',)
    readonly_fields = ('triggered_at', 'last_updated_at')
    actions = ['resolve_selected']

    def resolve_selected(self, request, queryset):
        for alert in queryset.filter(is_resolved=False):
            alert.resolve()
        self.message_user(request, f'{queryset.count()} alert(s) resolved.')
    resolve_selected.short_description = 'Mark selected alerts as resolved'
