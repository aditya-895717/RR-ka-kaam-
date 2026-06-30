from django.urls import path
from . import api

urlpatterns = [
    path('partners/laundry/',                   api.LaundryPartnerListAPI.as_view(),  name='api_hospital_laundry_partners'),
    path('partners/delivery/',                  api.DeliveryPartnerListAPI.as_view(), name='api_hospital_delivery_partners'),
    path('orders/',                             api.CreateOrderAPI.as_view(),          name='api_hospital_create_order'),
    path('orders/<uuid:order_id>/',             api.OrderDetailAPI.as_view(),          name='api_hospital_order_detail'),
    path('orders/<uuid:order_id>/confirm-delivery/', api.ConfirmDeliveryAPI.as_view(), name='api_hospital_confirm_delivery'),
]
