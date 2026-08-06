#!/usr/bin/env bash
# Vercel @vercel/static-build step.
#
# Collects static assets into static_collected/, which vercel.json publishes to
# the CDN and serves directly at /static/*. The Python lambda therefore never
# has to serve static files itself.
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 manage.py collectstatic --noinput --clear
