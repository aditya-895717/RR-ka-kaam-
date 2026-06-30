import logging

logger = logging.getLogger(__name__)


def create_invoice_for_order(order):
    """Bridge called from rfid.engine and hospital.views after S4 delivery."""
    from .engine import generate_invoice
    return generate_invoice(order.order_id)
