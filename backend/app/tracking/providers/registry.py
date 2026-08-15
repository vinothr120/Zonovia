from app.tracking.providers.base import TrackingProvider

_registry: dict[str, TrackingProvider] = {}


def register_provider(provider: TrackingProvider) -> None:
    _registry[provider.provider_type] = provider


def get_provider(provider_type: str) -> TrackingProvider | None:
    return _registry.get(provider_type)


def get_registered_providers() -> dict[str, TrackingProvider]:
    return dict(_registry)
