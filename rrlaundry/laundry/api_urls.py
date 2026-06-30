from django.urls import path

from . import api

urlpatterns = [
    path('floor/',                              api.FloorListAPI.as_view(),        name='api_laundry_floor'),
    path('items/<str:tag_number>/update-stage/', api.UpdateItemStageAPI.as_view(), name='api_laundry_update_stage'),
    path('items/<str:tag_number>/assign-worker/', api.AssignWorkerAPI.as_view(),  name='api_laundry_assign_worker'),
    path('alerts/',                             api.AlertListAPI.as_view(),        name='api_laundry_alerts'),
    path('alerts/<int:pk>/resolve/',            api.ResolveAlertAPI.as_view(),     name='api_laundry_resolve_alert'),
    path('pricing/update/',                     api.UpdatePricingAPI.as_view(),    name='api_laundry_update_pricing'),
]
