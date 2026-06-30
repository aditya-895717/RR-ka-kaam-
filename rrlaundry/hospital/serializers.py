from rest_framework import serializers

from accounts.models import DeliveryProfile, LaundryProfile
from .models import ItemType, LaundryOrder, OrderItem


class LaundryPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaundryProfile
        fields = ['id', 'business_name', 'area', 'city', 'phone_number', 'price_per_item', 'is_available']


class DeliveryPartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryProfile
        fields = ['id', 'city', 'area', 'phone_number', 'vehicle_type', 'is_available']


class OrderItemSerializer(serializers.ModelSerializer):
    item_type_label   = serializers.CharField(source='get_item_type_display', read_only=True)
    hospital_status   = serializers.SerializerMethodField()

    class Meta:
        model  = OrderItem
        fields = ['id', 'tag_number', 'item_type', 'item_type_label', 'hospital_status', 'added_at']

    def get_hospital_status(self, obj):
        return obj.hospital_status_label()


class LaundryOrderSerializer(serializers.ModelSerializer):
    items               = OrderItemSerializer(many=True, read_only=True)
    short_id            = serializers.CharField(read_only=True)
    hospital_status     = serializers.SerializerMethodField()
    department_name     = serializers.CharField(source='department.department_name', read_only=True)
    laundry_partner_name = serializers.CharField(source='laundry_partner.business_name', read_only=True)
    delivery_partner_name = serializers.SerializerMethodField()

    class Meta:
        model  = LaundryOrder
        fields = [
            'order_id', 'short_id', 'status', 'hospital_status',
            'department_name', 'laundry_partner_name', 'delivery_partner_name',
            'created_at', 'updated_at', 'items',
        ]

    def get_hospital_status(self, obj):
        return obj.hospital_status_label()

    def get_delivery_partner_name(self, obj):
        if obj.delivery_partner:
            u = obj.delivery_partner.user
            return u.full_name or u.email
        return None


class CreateOrderSerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=200,
    )

    def validate_items(self, value):
        valid_types = {c[0] for c in ItemType.choices}
        seen = set()
        for item in value:
            tag  = str(item.get('tag_number', '')).strip().upper()
            itype = item.get('item_type', '')
            if not tag:
                raise serializers.ValidationError('tag_number is required on each item.')
            if itype not in valid_types:
                raise serializers.ValidationError(f'Invalid item_type: {itype}')
            if tag in seen:
                raise serializers.ValidationError(f'Duplicate tag_number: {tag}')
            seen.add(tag)
            item['tag_number'] = tag
        return value
