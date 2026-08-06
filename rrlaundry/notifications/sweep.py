"""
notifications/sweep.py — HTTP-triggered replacement for the django-q2 worker.

Vercel's Python runtime is serverless and has no long-lived process type, so the
1-hour missing-item detection can no longer run as a background cluster. It is
instead driven by an external pinger (cron-job.org free tier) calling this
endpoint every 5 minutes.

This is deliberately NOT /ping/. /ping/ is an unauthenticated liveness probe and
must stay cheap and side-effect-free; this endpoint mutates data and is therefore
token-protected.

Auth: shared secret in either
    Authorization: Bearer <SWEEP_TOKEN>
    X-Sweep-Token: <SWEEP_TOKEN>
    ?token=<SWEEP_TOKEN>          (query param — for pingers that cannot set headers)

Responses:
    200  {"status": "ok", "alerts_created": N, ...}
    401  token missing
    403  token present but wrong
    503  SWEEP_TOKEN not configured server-side (fail closed, never run unguarded)
"""

import hmac
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _extract_token(request):
    """Pull the caller's token from header or query param. None if absent."""
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if auth.startswith('Bearer '):
        return auth[len('Bearer '):].strip()

    header_token = request.META.get('HTTP_X_SWEEP_TOKEN', '').strip()
    if header_token:
        return header_token

    query_token = request.GET.get('token', '').strip()
    if query_token:
        return query_token

    return None


@csrf_exempt
def sweep(request):
    """Run the missing-item sweep. GET and POST both accepted (pingers vary)."""
    expected = getattr(settings, 'SWEEP_TOKEN', '') or ''

    # Fail closed: an unset token must never mean "open to everyone".
    if not expected:
        logger.error('sweep: SWEEP_TOKEN is not configured — refusing to run.')
        return JsonResponse(
            {'error': 'Sweep endpoint is not configured.'}, status=503,
        )

    provided = _extract_token(request)
    if provided is None:
        return JsonResponse({'error': 'Missing token.'}, status=401)

    # Constant-time compare — avoids leaking the token via response timing.
    if not hmac.compare_digest(provided, expected):
        logger.warning('sweep: rejected request with invalid token.')
        return JsonResponse({'error': 'Invalid token.'}, status=403)

    from notifications.jobs import check_missing_items

    try:
        result = check_missing_items()
    except Exception:
        logger.exception('sweep: check_missing_items() failed')
        return JsonResponse({'error': 'Sweep failed.'}, status=500)

    return JsonResponse({
        'status': 'ok',
        'alerts_created': result['created'],
        'alerts_escalated': result['escalated'],
    })
