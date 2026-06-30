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
2. Migrations run automatically during Render build
3. Run `python manage.py createsuperuser` via Render Shell
4. In Django admin → Sites: set domain to `rrlaundry.onrender.com`
5. In Django admin → Social Applications: add Google app with client ID and secret
6. Verify SQLite disk is mounted at `/data/`
7. Send a test OTP email to confirm Brevo delivery

## RFID Scan Chain

```
S1 Pickup (hospital) → S2 Received (plant) → S3 Dispatch (plant) → S4 Delivery (hospital)
```

Each scan point triggers reconciliation, status updates, and email notifications.
