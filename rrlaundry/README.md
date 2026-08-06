# RRLaundry

Hospital laundry management platform built with Django. Covers the full lifecycle from order creation through RFID-tracked pickup, washing, dispatch, and delivery — with billing, email notifications, and a partner discovery system.

## Architecture

Three role-based portals, routed by URL path on a single domain:

| Portal | URL | Roles |
|--------|-----|-------|
| Hospital | `/hospital/dashboard/` | Hospital Head, Hospital Staff |
| Laundry | `/laundry/dashboard/` | Laundry Admin, Laundry Worker |
| Delivery | `/delivery/dashboard/` | Delivery Partner |

## Tech Stack

- **Backend**: Django 4.2, Django REST Framework
- **Auth**: Custom AbstractBaseUser, OTP login, Google OAuth (django-allauth)
- **Email**: Brevo (sib-api-v3-sdk)
- **Templates**: Jinja2 + Bootstrap 5
- **Background jobs**: django-q2 (1-hour alert worker)
- **Static files**: WhiteNoise
- **Database**: SQLite (persistent disk on Render)

## Local Development

```bash
# 1. Clone the repo
git clone https://github.com/aditya-895717/RR-ka-kaam-.git
cd RR-ka-kaam-/rrlaundry

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env        # edit with your values

# 5. Run migrations
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser

# 7. Start dev server
python manage.py runserver

# 8. (Optional) Start background worker in a second terminal
python manage.py qcluster
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `BREVO_API_KEY` | Yes | Brevo transactional email API key |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `DEFAULT_FROM_EMAIL` | Yes | Verified sender email address |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated allowed hosts |
| `DATABASE_URL` | Production | `sqlite:////data/db.sqlite3` on Render |
| `DEBUG` | No | Defaults to `False` in production |

## Deployed Branch

**`Capture-The-Flag`** is the active deployment branch. Render auto-deploys from this branch on every push.

Live URL: [https://rrlaundry.onrender.com](https://rrlaundry.onrender.com)

## Post-Deployment Steps

1. Confirm Render is deploying from `Capture-The-Flag`
2. Migrations run automatically during Render build (`buildCommand` in render.yaml)
3. Via Render Shell, load the seed fixture (creates the required Site row):
   ```bash
   python manage.py loaddata core/fixtures/seed.json
   ```
4. Via Render Shell, create the superuser:
   ```bash
   python manage.py createsuperuser
   ```
5. In Django admin → Social Applications: add Google app with client ID and secret
6. Verify SQLite disk is mounted at `/data/`
7. Hit `GET /ping/` — confirm `{"status": "ok"}` response
8. Send a test OTP email to confirm Brevo delivery

## Database Backup and Restore

The SQLite database lives at `/data/db.sqlite3` on Render's persistent disk. Back up and restore via Render Shell:

```bash
# Back up to a timestamped file in /data/
python manage.py backup_data

# Restore from a specific backup (will prompt for confirmation)
python manage.py restore_data /data/db_backup_20260703_120000.sqlite3

# Restore without prompt (for scripts)
python manage.py restore_data /data/db_backup_20260703_120000.sqlite3 --no-confirm
```

## Background Jobs (django-q2)

`django-q2` is installed and configured but **the qcluster worker is not running in production** on Render's free tier (free plans allow only one web service). The `check_missing_items()` job — which creates `MissingItemAlert` records for items idle >60 minutes — will not fire automatically.

**Options if automated alerts are needed:**
- Upgrade to a paid Render plan and add a background worker service running `python manage.py qcluster`
- Configure a Render Cron Job to `POST` to an internal endpoint that calls `check_missing_items()` directly
- Accept manual alert creation in the admin for now

## RFID Scan Chain

```
S1 Pickup (hospital) → S2 Received (plant) → S3 Dispatch (plant) → S4 Delivery (hospital)
```

Each scan point triggers reconciliation, status updates, and email notifications.
