from rest_framework import serializers

from .models import DeliveryJob, JobStatus


class DeliveryJobSerializer(serializers.ModelSerializer):
    hospital_name    = serializers.CharField(source='order.hospital.hospital_name', read_only=True)
    hospital_address = serializers.CharField(source='order.hospital.hospital_address', read_only=True)
    order_short_id   = serializers.CharField(source='order.short_id', read_only=True)
    item_count       = serializers.SerializerMethodField()
    job_type_label   = serializers.CharField(source='get_job_type_display', read_only=True)
    status_label     = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model  = DeliveryJob
        fields = [
            'job_id', 'short_id', 'order_short_id',
            'job_type', 'job_type_label', 'status', 'status_label',
            'hospital_name', 'hospital_address',
            'item_count', 'assigned_at', 'started_at', 'completed_at',
        ]

    def get_item_count(self, obj):
        return obj.order.items.count()


class ScanSubmitSerializer(serializers.Serializer):
    tag_numbers = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=1,
    )
