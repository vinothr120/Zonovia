import uuid

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.asset_core.models import Asset, AssetCategory, AssetDocument, AssetIdentifier, AssetLocation, AssetType, Vendor
from app.core.base_repository import TenantScopedRepository


class AssetCategoryRepository(TenantScopedRepository[AssetCategory]):
    model = AssetCategory

    async def get_by_name(self, name: str) -> AssetCategory | None:
        stmt = self._base_query().where(AssetCategory.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AssetTypeRepository(TenantScopedRepository[AssetType]):
    model = AssetType

    async def get_by_name(self, name: str) -> AssetType | None:
        stmt = self._base_query().where(AssetType.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_category(self, category_id: uuid.UUID) -> list[AssetType]:
        stmt = self._base_query().where(AssetType.category_id == category_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class VendorRepository(TenantScopedRepository[Vendor]):
    model = Vendor


class AssetLocationRepository(TenantScopedRepository[AssetLocation]):
    model = AssetLocation

    async def get_by_name_under_parent(self, *, parent_location_id: uuid.UUID | None, name: str) -> AssetLocation | None:
        stmt = self._base_query().where(AssetLocation.parent_location_id == parent_location_id, AssetLocation.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_children(self, parent_location_id: uuid.UUID | None) -> list[AssetLocation]:
        stmt = self._base_query().where(AssetLocation.parent_location_id == parent_location_id).order_by(AssetLocation.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_roots(self) -> list[AssetLocation]:
        return await self.list_children(None)

    async def has_children(self, location_id: uuid.UUID) -> bool:
        stmt = self._base_query().where(AssetLocation.parent_location_id == location_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_descendants(self, location_id: uuid.UUID) -> list[AssetLocation]:
        """Recursive CTE walking parent_location_id downward from `location_id`. Excludes
        `location_id` itself. Portable to both SQLite-in-tests and Postgres via SQLAlchemy's
        dialect-generic `.cte(recursive=True)` — no ltree, no materialized path."""
        top = (
            select(AssetLocation)
            .where(AssetLocation.id == location_id, AssetLocation.tenant_id == self.tenant_id)
            .cte(name="location_descendants", recursive=True)
        )
        top_alias = aliased(AssetLocation, top)
        bottom = select(AssetLocation).where(
            AssetLocation.parent_location_id == top_alias.id,
            AssetLocation.tenant_id == self.tenant_id,
            AssetLocation.deleted_at.is_(None),
        )
        recursive_cte = top.union(bottom)
        cte_alias = aliased(AssetLocation, recursive_cte)
        stmt = select(cte_alias).where(cte_alias.id != location_id).order_by(cte_alias.sort_order)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_ancestors(self, location_id: uuid.UUID) -> list[AssetLocation]:
        """Recursive CTE walking parent_location_id upward from `location_id`. Excludes
        `location_id` itself; returns nearest ancestor first."""
        top = (
            select(AssetLocation)
            .where(AssetLocation.id == location_id, AssetLocation.tenant_id == self.tenant_id)
            .cte(name="location_ancestors", recursive=True)
        )
        top_alias = aliased(AssetLocation, top)
        bottom = select(AssetLocation).where(
            AssetLocation.id == top_alias.parent_location_id,
            AssetLocation.tenant_id == self.tenant_id,
            AssetLocation.deleted_at.is_(None),
        )
        recursive_cte = top.union(bottom)
        cte_alias = aliased(AssetLocation, recursive_cte)
        stmt = select(cte_alias).where(cte_alias.id != location_id)
        result = await self.session.execute(stmt)
        by_id = {row.id: row for row in result.scalars().all()}

        # A UNION CTE's row order isn't guaranteed to reflect traversal depth on every
        # dialect, so the nearest-first order is rebuilt by walking the parent chain in
        # Python from the starting node using the fetched ancestor set as a lookup.
        target = await self.get_by_id(location_id)
        ordered: list[AssetLocation] = []
        cursor = target.parent_location_id if target is not None else None
        while cursor is not None and cursor in by_id:
            node = by_id[cursor]
            ordered.append(node)
            cursor = node.parent_location_id
        return ordered


class AssetRepository(TenantScopedRepository[Asset]):
    model = Asset

    async def list_by_location(self, location_id: uuid.UUID) -> list[Asset]:
        stmt = self._base_query().where(Asset.current_location_id == location_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[Asset]:
        """Unpaginated — the inherited `list()` defaults to limit=20, which would silently
        truncate inventory scope resolution for any tenant with more than 20 assets. Only
        used by app.inventory.service.InventoryService.list_expected_assets."""
        stmt = self._base_query()
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_location_ids(self, location_ids: list[uuid.UUID]) -> list[Asset]:
        """IN-query variant of list_by_location, for a location-scoped inventory cycle whose
        asset set spans a root location plus every descendant returned by
        AssetLocationRepository.list_descendants."""
        if not location_ids:
            return []
        stmt = self._base_query().where(Asset.current_location_id.in_(location_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_lifecycle_state_id(self, state_id: uuid.UUID) -> list[Asset]:
        """Filters the existing Asset.current_lifecycle_state_id column only — this file still
        never imports anything from app.flow. Used by
        app.maintenance.service.MaintenanceService.list_tickets's lifecycle_state_key filter,
        which resolves the key to an id via the read-only
        app.flow.repository.LifecycleStateDefinitionRepository before calling this."""
        stmt = self._base_query().where(Asset.current_lifecycle_state_id == state_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AssetIdentifierRepository(TenantScopedRepository[AssetIdentifier]):
    model = AssetIdentifier

    async def get_by_type_value(self, *, identifier_type: str, value: str) -> AssetIdentifier | None:
        stmt = self._base_query().where(AssetIdentifier.identifier_type == identifier_type, AssetIdentifier.value == value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetIdentifier]:
        stmt = self._base_query().where(AssetIdentifier.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_primary_for_asset(self, asset_id: uuid.UUID) -> AssetIdentifier | None:
        stmt = self._base_query().where(AssetIdentifier.asset_id == asset_id, AssetIdentifier.is_primary.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AssetDocumentRepository(TenantScopedRepository[AssetDocument]):
    model = AssetDocument

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[AssetDocument]:
        stmt = self._base_query().where(AssetDocument.asset_id == asset_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
