"""app.users.service.grant_covers — Phase 0 only implements tenant-wide role scope (see
UserRole's docstring in app/users/models.py). This is the seam Phase 1's location-scoped
roles extend without a migration."""

from app.users.service import PermissionGrant, grant_covers


def test_tenant_scoped_grant_covers_the_matching_permission():
    grant = PermissionGrant(permission_key="users.view", scope_type="tenant", scope_id=None)
    assert grant_covers(grant, "users.view") is True


def test_grant_does_not_cover_a_different_permission_key():
    grant = PermissionGrant(permission_key="users.view", scope_type="tenant", scope_id=None)
    assert grant_covers(grant, "users.create") is False
