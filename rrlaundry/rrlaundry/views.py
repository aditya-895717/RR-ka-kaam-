import datetime

from django.http import JsonResponse


def ping(request):
    """
    Liveness probe. Nothing else.

    - No auth required.
    - Returns ONLY {"status": "ok", "ts": "<iso-8601>"} — no env/config leakage.
    - NO side effects. This endpoint used to run a missing-item sweep, which
      meant an unauthenticated caller could trigger database writes. Alert
      detection now lives behind the token-protected
      /api/notifications/sweep/ endpoint, so a health check is once again
      just a health check.
    """
    return JsonResponse({
        'status': 'ok',
        'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
