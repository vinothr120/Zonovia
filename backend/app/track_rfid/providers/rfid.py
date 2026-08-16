from app.tracking.providers.base import TrackingProvider


class RFIDProvider(TrackingProvider):
    """Registers into tracking-engine's existing provider registry (app.tracking.providers.
    registry) from OUTSIDE app/tracking/ — the same one-directional-dependency discipline
    TrackingProvider's own docstring describes. Once registered, /tracking/scan transparently
    accepts identifier_type="RFID_EPC" too — free reuse of the human-scan endpoint for a
    manual RFID lookup, no new endpoint needed for that case.

    RFID EPC values are dense hex-like tokens with no internal structure — like BarcodeProvider,
    any internal whitespace means a misread and is rejected outright. Additionally case-folds
    to uppercase (EPC hex is conventionally represented that way, and two different readers —
    or a human typing one in by hand via /tracking/scan — might report the same tag in
    different cases); QRProvider/BarcodeProvider don't need this since their values aren't
    conventionally cased."""

    provider_type = "RFID_EPC"

    def normalize(self, raw_value: str) -> str | None:
        value = raw_value.strip().upper()
        if not value or any(ch.isspace() for ch in value):
            return None
        return value
