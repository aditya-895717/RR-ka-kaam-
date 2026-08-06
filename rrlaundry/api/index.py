"""
Vercel Python runtime entrypoint.

@vercel/python detects a module-level WSGI callable named `app` and adapts it to
the serverless handler, so this file only has to expose Django's WSGI
application. All routing is delegated to Django via rrlaundry/urls.py; vercel.json
sends every non-/static/ request here.
"""

import os
import sys
from pathlib import Path

# The lambda's working directory is the repo root's parent-agnostic bundle root,
# so add the project root explicitly — otherwise `import rrlaundry` fails.
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rrlaundry.settings')

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()

# Vercel's handler discovery also accepts `application`; expose both so the
# entrypoint works regardless of which name the builder looks for.
application = app
