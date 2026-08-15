from app.tracking.providers.base import TrackingProvider


class QRProvider(TrackingProvider):
    """QR payloads are free-form text (URLs, JSON blobs, plain codes) — normalization only
    trims surrounding whitespace. Internal whitespace is left untouched since it can be
    meaningful content (e.g. a URL query string or a human-readable label), unlike
    BarcodeProvider below."""

    provider_type = "QR"

    def normalize(self, raw_value: str) -> str | None:
        value = raw_value.strip()
        return value or None
