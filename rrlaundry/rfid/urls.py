from django.urls import path

from . import views

urlpatterns = [
    path('tag/<str:tag_number>/', views.TagHistoryView.as_view(), name='rfid_tag_history'),
]
