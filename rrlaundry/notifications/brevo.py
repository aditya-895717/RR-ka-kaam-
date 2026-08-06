import logging

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_SENDER_NAME  = 'RRLaundry'
_SENDER_EMAIL = 'noreply@dubeyitsolution.tech'

_FOOTER = """
<hr style="border:none;border-top:1px solid #eee;margin:32px 0 16px;">
<p style="color:#bbb;font-size:11px;text-align:center;margin:0;">
  Dubey IT Solutions — RRLaundry
</p>
"""

# ─── Base sender ──────────────────────────────────────────────────────────────

def send_email(to_email, to_name, subject, html_content):
    """Send a transactional email via Brevo. Never raises — logs on failure."""
    api_key = getattr(settings, 'BREVO_API_KEY', '')
    if not api_key:
        logger.warning('BREVO_API_KEY not configured — email to %s suppressed', to_email)
        return False

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = api_key

    api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    payload = sib_api_v3_sdk.SendSmtpEmail(
        to=[{'email': to_email, 'name': to_name or to_email}],
        sender={'name': _SENDER_NAME, 'email': _SENDER_EMAIL},
        subject=subject,
        html_content=html_content,
    )
    try:
        response = api.send_transac_email(payload)
        logger.info('Email sent → %s (%s) message_id=%s',
                    to_email, subject, getattr(response, 'message_id', None))
        return True
    except ApiException as exc:
        logger.error('Brevo send_email failed for %s: %s',
                     to_email, getattr(exc, 'body', exc))
        return False
    except Exception as exc:
        logger.error('Unexpected error sending email to %s: %s', to_email, exc)
        return False


# ─── Email 1: OTP ─────────────────────────────────────────────────────────────

def send_otp_email(to_email, to_name, otp_code):
    subject = 'Your RRLaundry Login OTP'
    name    = to_name or 'there'
    html    = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:8px;">Your One-Time Password</h2>
  <p style="color:#555;margin-bottom:24px;">
    Hi {name},<br>
    Use the OTP below to sign in to your RRLaundry account.
    It expires in <strong>10 minutes</strong>.
  </p>
  <div style="background:#f4f4f4;border-radius:8px;padding:24px;text-align:center;margin-bottom:24px;">
    <span style="font-size:38px;font-weight:700;letter-spacing:10px;color:#003580;">{otp_code}</span>
  </div>
  <p style="color:#999;font-size:13px;">
    Do not share this OTP with anyone. RRLaundry will never ask for your OTP.
  </p>
  {_FOOTER}
</div>"""
    return send_email(to_email, to_name, subject, html)


# ─── Email 2: S1 Pickup notification ──────────────────────────────────────────

def send_pickup_notification(order, scanned_tags, delivery_partner_name):
    """Notify hospital head that items have been picked up (S1 scan)."""
    from django.db.models import Count
    from hospital.models import OrderItem

    to_email = order.hospital.user.email
    to_name  = order.hospital.user.full_name or order.hospital.hospital_name
    subject  = f'Pickup Confirmed — Order #{order.short_id}'
    now_str  = timezone.now().strftime('%d %B %Y, %H:%M')
    dp_name  = delivery_partner_name or '—'

    dept_data = (
        OrderItem.objects
        .filter(order=order, tag_number__in=scanned_tags)
        .values('department__department_name')
        .annotate(count=Count('id'))
        .order_by('department__department_name')
    )

    dept_rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;color:#444;">'
        f'{r["department__department_name"] or "Unassigned"}</td>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;'
        f'text-align:center;font-weight:600;color:#003580;">{r["count"]}</td>'
        f'</tr>'
        for r in dept_data
    )

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:4px;">Pickup Confirmed</h2>
  <p style="color:#888;font-size:13px;margin-bottom:24px;">Order #{order.short_id}</p>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">
    <tr>
      <td style="color:#888;padding:5px 0;width:160px;">Order ID</td>
      <td style="font-weight:600;">#{order.short_id}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Delivery Partner</td>
      <td>{dp_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Pickup Time</td>
      <td>{now_str}</td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;">
    <thead>
      <tr style="background:#f8fafc;">
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Department</th>
        <th style="padding:10px 14px;text-align:center;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Items Picked Up</th>
      </tr>
    </thead>
    <tbody>{dept_rows}</tbody>
    <tfoot>
      <tr style="background:#f8fafc;">
        <td style="padding:10px 14px;font-weight:700;color:#003580;">Total</td>
        <td style="padding:10px 14px;text-align:center;font-weight:700;
                   font-size:15px;color:#003580;">{len(scanned_tags)}</td>
      </tr>
    </tfoot>
  </table>

  <p style="color:#666;font-size:13px;margin-top:20px;">
    Items are on their way to the laundry plant. You will be notified once
    they are dispatched back to your facility.
  </p>
  {_FOOTER}
</div>"""
    return send_email(to_email, to_name, subject, html)


# ─── Email 3: S4 Delivery notification ────────────────────────────────────────

def send_delivery_notification(order, delivered_tags, missing_tags, delivery_partner_name):
    """Notify hospital head of delivery outcome (S4 scan)."""
    from django.db.models import Count
    from hospital.models import OrderItem

    to_email = order.hospital.user.email
    to_name  = order.hospital.user.full_name or order.hospital.hospital_name
    subject  = f'Delivery Complete — Order #{order.short_id}'
    now_str  = timezone.now().strftime('%d %B %Y, %H:%M')
    dp_name  = delivery_partner_name or '—'

    dept_data = (
        OrderItem.objects
        .filter(order=order, tag_number__in=delivered_tags)
        .values('department__department_name')
        .annotate(count=Count('id'))
        .order_by('department__department_name')
    ) if delivered_tags else []

    dept_rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;color:#444;">'
        f'{r["department__department_name"] or "Unassigned"}</td>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;'
        f'text-align:center;font-weight:600;color:#166534;">{r["count"]}</td>'
        f'</tr>'
        for r in dept_data
    )

    missing_section = ''
    if missing_tags:
        tag_chips = ' '.join(
            f'<code style="background:#fff0f0;border:1px solid #f5c0c0;'
            f'padding:2px 7px;border-radius:4px;font-size:12px;">{t}</code>'
            for t in missing_tags
        )
        missing_section = f"""
  <div style="background:#fff0f0;border:1px solid #f5c0c0;border-radius:6px;
              padding:16px 18px;margin-top:20px;font-size:13px;">
    <strong style="color:#c00;">{len(missing_tags)} Item(s) Not Delivered</strong>
    <p style="color:#900;margin:8px 0 6px;">
      The following tags were expected but not scanned at delivery:
    </p>
    <p style="margin:0 0 8px;">{tag_chips}</p>
    <p style="color:#900;font-size:12px;margin:0;">
      Our team will investigate. Please contact your laundry partner for follow-up.
    </p>
  </div>"""

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:4px;">Delivery Complete</h2>
  <p style="color:#888;font-size:13px;margin-bottom:24px;">Order #{order.short_id}</p>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">
    <tr>
      <td style="color:#888;padding:5px 0;width:160px;">Order ID</td>
      <td style="font-weight:600;">#{order.short_id}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Delivery Partner</td>
      <td>{dp_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Delivery Time</td>
      <td>{now_str}</td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;">
    <thead>
      <tr style="background:#f8fafc;">
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Department</th>
        <th style="padding:10px 14px;text-align:center;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Items Delivered</th>
      </tr>
    </thead>
    <tbody>{dept_rows}</tbody>
    <tfoot>
      <tr style="background:#f8fafc;">
        <td style="padding:10px 14px;font-weight:700;color:#003580;">Total Delivered</td>
        <td style="padding:10px 14px;text-align:center;font-weight:700;
                   font-size:15px;color:#166534;">{len(delivered_tags)}</td>
      </tr>
    </tfoot>
  </table>
  {missing_section}

  <p style="color:#666;font-size:13px;margin-top:20px;">
    Please confirm receipt on your hospital portal to close this order.
  </p>
  {_FOOTER}
</div>"""
    return send_email(to_email, to_name, subject, html)


# ─── Email 4: Invoice ─────────────────────────────────────────────────────────

def send_invoice_email(invoice):
    """Send invoice to hospital head."""
    to_email      = invoice.hospital.user.email
    to_name       = invoice.hospital.user.full_name or invoice.hospital.hospital_name
    subject       = f'Invoice #{invoice.invoice_number} — RRLaundry'
    generated_str = invoice.generated_at.strftime('%d %B %Y')
    due_str       = invoice.due_date.strftime('%d %B %Y')
    laundry_name  = invoice.laundry_partner.business_name if invoice.laundry_partner else '—'

    line_rows = ''.join(
        f'<tr>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;color:#444;">'
        f'{li.department.department_name if li.department else "Unassigned"}</td>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;text-align:center;">{li.item_count}</td>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;'
        f'text-align:right;color:#888;">₹{li.price_per_item}</td>'
        f'<td style="padding:8px 14px;border-bottom:1px solid #f0f4f8;'
        f'text-align:right;font-weight:600;">₹{li.line_total}</td>'
        f'</tr>'
        for li in invoice.line_items.select_related('department').all()
    )

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:4px;">Invoice #{invoice.invoice_number}</h2>
  <p style="color:#888;font-size:13px;margin-bottom:24px;">Generated on {generated_str}</p>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">
    <tr>
      <td style="color:#888;padding:5px 0;width:160px;">Hospital</td>
      <td style="font-weight:600;">{invoice.hospital.hospital_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Laundry Partner</td>
      <td>{laundry_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Invoice Date</td>
      <td>{generated_str}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:5px 0;">Due Date</td>
      <td style="color:#c00;font-weight:600;">{due_str}</td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">
    <thead>
      <tr style="background:#f8fafc;">
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Department</th>
        <th style="padding:10px 14px;text-align:center;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Items</th>
        <th style="padding:10px 14px;text-align:right;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Rate</th>
        <th style="padding:10px 14px;text-align:right;font-size:11px;color:#6b7280;
                   text-transform:uppercase;letter-spacing:.5px;">Amount</th>
      </tr>
    </thead>
    <tbody>{line_rows}</tbody>
    <tfoot>
      <tr style="background:#f8fafc;">
        <td colspan="3" style="padding:12px 14px;font-weight:700;
                               color:#003580;text-align:right;">
          Total ({invoice.total_items} items)
        </td>
        <td style="padding:12px 14px;font-weight:700;font-size:16px;
                   color:#003580;text-align:right;">₹{invoice.total_amount}</td>
      </tr>
    </tfoot>
  </table>

  <div style="background:#fff7e6;border-radius:6px;padding:16px 18px;
              font-size:13px;color:#92400e;margin-bottom:24px;">
    <strong>Payment Instructions:</strong> Process payment to the laundry partner and
    mark this invoice as paid from your Hospital Portal → Invoices by
    <strong>{due_str}</strong>.
  </div>
  {_FOOTER}
</div>"""
    return send_email(to_email, to_name, subject, html)


# ─── Email 5: New job assigned (delivery partner) ─────────────────────────────

def send_job_assigned_email(delivery_partner_email, delivery_partner_name, order, job_type):
    """Notify a delivery partner of a new pickup or delivery job."""
    subject    = f'New {job_type} Job Assigned — Order #{order.short_id}'
    item_count = order.items.count()
    dept_name  = order.department.department_name if order.department else '—'

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:4px;">New {job_type} Job</h2>
  <p style="color:#888;font-size:13px;margin-bottom:24px;">Order #{order.short_id}</p>

  <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:24px;">
    <tr>
      <td style="color:#888;padding:7px 0;width:160px;">Job Type</td>
      <td style="font-weight:600;color:#003580;">{job_type}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:7px 0;">Hospital</td>
      <td style="font-weight:600;">{order.hospital.hospital_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:7px 0;">Address</td>
      <td>{order.hospital.hospital_address}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:7px 0;">Department</td>
      <td>{dept_name}</td>
    </tr>
    <tr>
      <td style="color:#888;padding:7px 0;">Expected Items</td>
      <td style="font-weight:600;">{item_count}</td>
    </tr>
  </table>

  <p style="color:#666;font-size:13px;">
    Log in to your RRLaundry Delivery Portal to scan items and confirm this job.
  </p>
  {_FOOTER}
</div>"""
    return send_email(delivery_partner_email, delivery_partner_name, subject, html)
