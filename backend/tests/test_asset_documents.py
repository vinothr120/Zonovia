"""app.asset_core.service.AssetService.upload_document — mirrors SchoolAssist's
FileService.upload exactly (content-type/size validation, sha256 checksum, audit log) via the
ported app/core/storage.py. tests/conftest.py routes the LocalStorageBackend at a throwaway
system temp dir for the whole test run."""

from tests.conftest import make_role_with_permissions, make_tenant, make_user_with_role

_DOCUMENT_PERMS = ["assets.view", "assets.create", "assets.manage_documents", "asset_catalog.manage"]


async def _make_document_user(db, tenant):
    role = await make_role_with_permissions(db, tenant_id=None, name="DocumentUser", permission_keys=_DOCUMENT_PERMS)
    user, token = await make_user_with_role(db, tenant_id=tenant.id, email="docuser@asset-documents-test.example", role=role)
    return user, token


async def _create_asset(client, headers):
    category = (await client.post("/api/v1/asset-categories", json={"name": "IT"}, headers=headers)).json()["data"]
    asset_type = (
        await client.post("/api/v1/asset-types", json={"category_id": category["id"], "name": "Printer"}, headers=headers)
    ).json()["data"]
    asset = (
        await client.post(
            "/api/v1/assets", json={"name": "Document Test Asset", "asset_type_id": asset_type["id"]}, headers=headers
        )
    ).json()["data"]
    return asset


async def test_upload_download_and_delete_document(client, db):
    tenant = await make_tenant(db, subdomain="asset-documents-happy-path")
    _user, token = await _make_document_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    content = b"%PDF-1.4 fake receipt content"

    upload_resp = await client.post(
        f"/api/v1/assets/{asset['id']}/documents",
        files={"upload": ("receipt.pdf", content, "application/pdf")},
        data={"document_type": "receipt"},
        headers=headers,
    )
    assert upload_resp.status_code == 201, upload_resp.text
    document = upload_resp.json()["data"]
    assert document["original_filename"] == "receipt.pdf"
    assert document["content_type"] == "application/pdf"
    assert document["size_bytes"] == len(content)
    assert document["document_type"] == "receipt"
    assert len(document["checksum"]) == 64  # sha256 hex

    list_resp = await client.get(f"/api/v1/assets/{asset['id']}/documents", headers=headers)
    assert list_resp.status_code == 200
    assert any(d["id"] == document["id"] for d in list_resp.json()["data"])

    meta_resp = await client.get(f"/api/v1/assets/{asset['id']}/documents/{document['id']}", headers=headers)
    assert meta_resp.status_code == 200

    content_resp = await client.get(f"/api/v1/assets/{asset['id']}/documents/{document['id']}/content", headers=headers)
    assert content_resp.status_code == 200
    assert content_resp.content == content
    assert content_resp.headers["content-type"].startswith("application/pdf")

    delete_resp = await client.delete(f"/api/v1/assets/{asset['id']}/documents/{document['id']}", headers=headers)
    assert delete_resp.status_code == 204

    after_delete = await client.get(f"/api/v1/assets/{asset['id']}/documents/{document['id']}", headers=headers)
    assert after_delete.status_code == 404


async def test_upload_rejects_a_disallowed_content_type(client, db):
    tenant = await make_tenant(db, subdomain="asset-documents-bad-type")
    _user, token = await _make_document_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(
        f"/api/v1/assets/{asset['id']}/documents",
        files={"upload": ("script.exe", b"MZ\x90\x00", "application/x-msdownload")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_upload_rejects_an_oversized_file(client, db):
    tenant = await make_tenant(db, subdomain="asset-documents-oversized")
    _user, token = await _make_document_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    oversized = b"0" * (10 * 1024 * 1024 + 1)  # settings.file_max_size_bytes default is 10 MB
    resp = await client.post(
        f"/api/v1/assets/{asset['id']}/documents",
        files={"upload": ("huge.pdf", oversized, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_upload_rejects_an_empty_file(client, db):
    tenant = await make_tenant(db, subdomain="asset-documents-empty")
    _user, token = await _make_document_user(db, tenant)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    asset = await _create_asset(client, headers)
    resp = await client.post(
        f"/api/v1/assets/{asset['id']}/documents",
        files={"upload": ("empty.pdf", b"", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_document_endpoints_require_permission(client, db):
    tenant = await make_tenant(db, subdomain="asset-documents-perm-guard")
    role = await make_role_with_permissions(
        db, tenant_id=None, name="NoDocumentPerms", permission_keys=["assets.view", "assets.create"]
    )
    _user, token = await make_user_with_role(db, tenant_id=tenant.id, email="nodocperm@asset-documents-test.example", role=role)
    await db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    fake_asset_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"/api/v1/assets/{fake_asset_id}/documents",
        files={"upload": ("x.pdf", b"content", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 403
