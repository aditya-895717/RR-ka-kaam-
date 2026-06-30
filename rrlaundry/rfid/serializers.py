from rest_framework import serializers

from .models import ReconciliationLog, RFIDScanEvent


class RFIDScanInputSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=1,
        max_length=500,
    )

    def validate_tags(self, value):
        cleaned = [t.strip().upper() for t in value if t.strip()]
        if not cleaned:
            raise serializers.ValidationError('tags list cannot be empty.')
        if len(set(cleaned)) != len(cleaned):
            raise serializers.ValidationError('Duplicate tag numbers in request.')
        return cleaned


class RFIDScanEventSerializer(serializers.ModelSerializer):
    scanned_by_name  = serializers.SerializerMethodField()
    scan_point_label = serializers.CharField(source='get_scan_point_display', read_only=True)
    order_short_id   = serializers.CharField(source='order.short_id', read_only=True)
    hospital_name    = serializers.CharField(source='order.hospital.hospital_name', read_only=True)

    class Meta:
        model = RFIDScanEvent
        fields = [
            'scan_id', 'tag_number', 'scan_point', 'scan_point_label',
            'scanned_at', 'scanned_by_name', 'location_note',
            'order_short_id', 'hospital_name',
        ]

    def get_scanned_by_name(self, obj):
        if obj.scanned_by:
            return obj.scanned_by.full_name or obj.scanned_by.email
        return None


class OrderReconciliationSerializer(serializers.ModelSerializer):
    scan_point_from_label = serializers.CharField(
        source='get_scan_point_from_display', read_only=True,
    )
    scan_point_to_label = serializers.CharField(
        source='get_scan_point_to_display', read_only=True,
    )
    order_short_id = serializers.CharField(source='order.short_id', read_only=True)

    class Meta:
        model = ReconciliationLog
        fields = [
            'id', 'order_short_id',
            'scan_point_from', 'scan_point_from_label',
            'scan_point_to', 'scan_point_to_label',
            'expected_count', 'received_count', 'missing_tags',
            'is_matched', 'logged_at',
        ]
