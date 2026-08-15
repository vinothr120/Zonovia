"""TrackingProvider unit tests — QRProvider vs BarcodeProvider's genuinely distinct
normalize() behavior (barcode rejects internal whitespace, QR doesn't), plus the provider
registry module (register_provider/get_provider/get_registered_providers), which structurally
mirrors app/core/module_registry.py."""

from app.tracking.providers.barcode import BarcodeProvider
from app.tracking.providers.qr import QRProvider
from app.tracking.providers.registry import get_provider, get_registered_providers, register_provider


def test_qr_provider_trims_surrounding_whitespace_but_keeps_internal_whitespace():
    provider = QRProvider()
    assert provider.normalize("  https://example.com/asset 42  ") == "https://example.com/asset 42"


def test_qr_provider_rejects_empty_value():
    provider = QRProvider()
    assert provider.normalize("   ") is None


def test_barcode_provider_trims_surrounding_whitespace():
    provider = BarcodeProvider()
    assert provider.normalize("  012345678905  ") == "012345678905"


def test_barcode_provider_rejects_internal_whitespace():
    """The genuinely distinct behavior vs QRProvider — a real barcode scan never contains a
    space; internal whitespace here means a misread, so it's rejected outright."""
    provider = BarcodeProvider()
    assert provider.normalize("0123 45678905") is None


def test_barcode_provider_rejects_empty_value():
    provider = BarcodeProvider()
    assert provider.normalize("   ") is None


def test_registry_round_trips_a_provider():
    provider = QRProvider()
    register_provider(provider)
    assert get_provider("QR") is provider


def test_registry_returns_none_for_unregistered_type():
    assert get_provider("does-not-exist") is None


def test_get_registered_providers_returns_a_copy_not_the_live_registry():
    register_provider(QRProvider())
    snapshot = get_registered_providers()
    snapshot["QR"] = None
    assert get_provider("QR") is not None
