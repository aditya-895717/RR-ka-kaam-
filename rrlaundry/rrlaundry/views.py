import datetime
import os
from django.http import JsonResponse


def ping(request):
    brevo_key = os.environ.get('BREVO_API_KEY')
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
    google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    return JsonResponse({
        "status": "ok",
        "service": "rrlaundry",
        "timestamp": str(datetime.datetime.now()),
        "email_configured": bool(brevo_key),
        "google_signin_configured": bool(google_client_id and google_client_secret),
    })
