from app.tracking.providers.base import TrackingProvider


class BarcodeProvider(TrackingProvider):
    """1D barcodes (CODE_128, EAN_13, UPC_A, CODE_39, ...) encode a single dense token with no
    internal structure — any internal whitespace means the scan was malformed or misread, so
    (unlike QRProvider) it's rejected outright rather than passed through."""

    provider_type = "BARCODE"

    def normalize(self, raw_value: str) -> str | None:
        value = raw_value.strip()
        if not value or any(ch.isspace() for ch in value):
            return None
        return value
