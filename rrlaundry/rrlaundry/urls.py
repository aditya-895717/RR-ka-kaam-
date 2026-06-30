from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rrlaundry.views import ping

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),   # custom auth — takes priority over allauth
    path('accounts/', include('allauth.urls')),    # allauth social OAuth callbacks
    path('', include('core.urls')),
    path('hospital/', include('hospital.urls')),
    path('api/hospital/', include('hospital.api_urls')),
    path('api/laundry/', include('laundry.api_urls')),
    path('api/delivery/', include('delivery.api_urls')),
    path('api/rfid/', include('rfid.api_urls')),
    path('api/billing/', include('billing.api_urls')),
    path('api/discovery/', include('core.api_urls')),
    path('api/notifications/', include('notifications.api_urls')),
    path('laundry/', include('laundry.urls')),
    path('delivery/', include('delivery.urls')),
    path('rfid/', include('rfid.urls')),
    path('billing/', include('billing.urls')),
    path('notifications/', include('notifications.urls')),
    path('ping/', ping, name='ping'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
