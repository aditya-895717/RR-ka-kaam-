from rest_framework import serializers

from hospital.models import OrderItem
from .models import FloorStage, ItemStageLog, MissingItemAlert, WorkerItemAssignment


class FloorItemSerializer(serializers.ModelSerializer):
    hospital_name    = serializers.CharField(source='order.hospital.hospital_name', read_only=True)
    department_name  = serializers.CharField(source='department.department_name', read_only=True, default='—')
    item_type_label  = serializers.CharField(source='get_item_type_display', read_only=True)
    floor_stage      = serializers.SerializerMethodField()
    stage_updated_at = serializers.SerializerMethodField()
    first_worker     = serializers.SerializerMethodField()
    has_alert        = serializers.SerializerMethodField()

    class Meta:
        model  = OrderItem
        fields = [
            'id', 'tag_number', 'item_type', 'item_type_label',
            'hospital_name', 'department_name',
            'floor_stage', 'stage_updated_at', 'first_worker', 'has_alert',
        ]

    def get_floor_stage(self, obj):
        log = obj.stage_logs.first()
        return log.stage if log else None

    def get_stage_updated_at(self, obj):
        log = obj.stage_logs.first()
        return log.updated_at if log else None

    def get_first_worker(self, obj):
        wa = obj.worker_assignments.filter(is_first_worker=True).first()
        if wa and wa.worker:
            return {'id': wa.worker.id, 'name': wa.worker.full_name or wa.worker.email}
        return None

    def get_has_alert(self, obj):
        return obj.alerts.filter(is_resolved=False).exists()


class StageUpdateSerializer(serializers.Serializer):
    new_stage  = serializers.ChoiceField(choices=FloorStage.choices)
    worker_id  = serializers.UUIDField(required=False, allow_null=True)
    notes      = serializers.CharField(required=False, allow_blank=True, default='')


class WorkerAssignSerializer(serializers.Serializer):
    worker_id = serializers.UUIDField()


class AlertSerializer(serializers.ModelSerializer):
    tag_number      = serializers.CharField(source='order_item.tag_number', read_only=True)
    hospital_name   = serializers.CharField(source='order_item.order.hospital.hospital_name', read_only=True)
    last_stage_label = serializers.CharField(source='get_last_stage_display', read_only=True)
    worker_name     = serializers.SerializerMethodField()
    minutes_stale   = serializers.SerializerMethodField()

    class Meta:
        model  = MissingItemAlert
        fields = [
            'id', 'tag_number', 'hospital_name',
            'last_stage', 'last_stage_label',
            'triggered_at', 'last_updated_at', 'minutes_stale',
            'worker_name', 'is_resolved', 'resolved_at',
        ]

    def get_worker_name(self, obj):
        if obj.assigned_worker:
            return obj.assigned_worker.full_name or obj.assigned_worker.email
        return None

    def get_minutes_stale(self, obj):
        return obj.minutes_since_last_update()


class PricingUpdateSerializer(serializers.Serializer):
    price_per_item = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0)
