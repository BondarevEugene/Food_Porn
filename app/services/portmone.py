"""Compatibility shim: a payment URL requires a server-issued invoice."""
from app.services.payment import PaymentError


def get_portmone_payment_url(*args, **kwargs) -> str:
    raise PaymentError("Create a provider invoice with PaymentService.create_portmone_invoice()")
