from django.urls import path
from . import api

urlpatterns = [
    path('laundry-partners/',  api.LaundryPartnerDiscoveryAPI.as_view(), name='api_discovery_laundry'),
    path('delivery-partners/', api.DeliveryPartnerDiscoveryAPI.as_view(), name='api_discovery_delivery'),
    path('select-partners/',   api.SelectPartnersAPI.as_view(),           name='api_discovery_select'),
]
