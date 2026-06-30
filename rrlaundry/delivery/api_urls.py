from django.urls import path

from .api import (
    CompleteDeliveryAPI, CompletePickupAPI,
    JobDetailAPI, JobListAPI, StartJobAPI,
)

urlpatterns = [
    path('jobs/',                         JobListAPI.as_view(),         name='api_delivery_job_list'),
    path('jobs/<uuid:job_id>/',           JobDetailAPI.as_view(),       name='api_delivery_job_detail'),
    path('jobs/<uuid:job_id>/start/',     StartJobAPI.as_view(),        name='api_delivery_start_job'),
    path('jobs/<uuid:job_id>/pickup/',    CompletePickupAPI.as_view(),  name='api_delivery_complete_pickup'),
    path('jobs/<uuid:job_id>/delivery/',  CompleteDeliveryAPI.as_view(), name='api_delivery_complete_delivery'),
]
