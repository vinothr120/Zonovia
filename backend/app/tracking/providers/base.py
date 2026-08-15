from abc import ABC, abstractmethod


class TrackingProvider(ABC):
    """A pluggable scan-code normalizer — one implementation per identifier_type this module
    knows how to resolve. Providers register themselves through
    app/tracking/providers/registry.py rather than being imported directly by
    app/tracking/service.py, so a later phase's provider (e.g. Phase 6's track_rfid module
    registering an RFIDProvider) can extend tracking-engine without app/tracking/ ever
    importing from it — the same one-directional-dependency discipline enforced everywhere
    else in this codebase (core -> asset-core -> flow, asset-core -> tracking-engine)."""

    provider_type: str  # matches AssetIdentifier.identifier_type / TrackingEvent.provider_type

    @abstractmethod
    def normalize(self, raw_value: str) -> str | None:
        """Returns the canonical form of a scanned value, or None if raw_value is malformed
        for this provider's format. TrackingService.record_scan treats None as a 422 —
        distinct from an unresolved-but-well-formed value, which is a 404."""
        raise NotImplementedError
