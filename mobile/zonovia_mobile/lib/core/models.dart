/// Manual `fromJson` models mirroring the backend Pydantic schemas field-for-field.
/// No codegen package (json_serializable etc.) — consistent with the sibling apps'
/// hand-written-model convention.
library;

/// Mirrors backend/app/users/schemas.py's UserRoleRead.
class UserRoleRead {
  final String id;
  final String roleId;
  final String roleName;
  final String scopeType;
  final String? scopeId;

  UserRoleRead({
    required this.id,
    required this.roleId,
    required this.roleName,
    required this.scopeType,
    required this.scopeId,
  });

  factory UserRoleRead.fromJson(Map<String, dynamic> json) => UserRoleRead(
        id: json['id'] as String,
        roleId: json['role_id'] as String,
        roleName: json['role_name'] as String,
        scopeType: json['scope_type'] as String,
        scopeId: json['scope_id'] as String?,
      );
}

/// Mirrors backend/app/users/schemas.py's MeRead (which extends UserRead).
class Me {
  final String id;
  final String email;
  final String? phone;
  final String status;
  final bool mfaEnabled;
  final DateTime? lastLoginAt;
  final DateTime createdAt;
  final List<UserRoleRead> roles;
  final bool isPlatformAdmin;
  final List<String> permissions;

  Me({
    required this.id,
    required this.email,
    required this.phone,
    required this.status,
    required this.mfaEnabled,
    required this.lastLoginAt,
    required this.createdAt,
    required this.roles,
    required this.isPlatformAdmin,
    required this.permissions,
  });

  factory Me.fromJson(Map<String, dynamic> json) => Me(
        id: json['id'] as String,
        email: json['email'] as String,
        phone: json['phone'] as String?,
        status: json['status'] as String,
        mfaEnabled: json['mfa_enabled'] as bool,
        lastLoginAt: json['last_login_at'] != null ? DateTime.parse(json['last_login_at'] as String) : null,
        createdAt: DateTime.parse(json['created_at'] as String),
        roles: (json['roles'] as List? ?? [])
            .map((r) => UserRoleRead.fromJson(r as Map<String, dynamic>))
            .toList(),
        isPlatformAdmin: json['is_platform_admin'] as bool? ?? false,
        permissions: (json['permissions'] as List? ?? []).cast<String>(),
      );
}

/// Mirrors backend/app/tracking/schemas.py's AssetSummary — just enough for the
/// scan result card without a second round trip (asset_core owns the full AssetRead).
class AssetSummary {
  final String id;
  final String name;
  final String assetTypeId;
  final String? currentLocationId;
  final String? currentLifecycleStateId;
  final String? currentCustodianId;

  AssetSummary({
    required this.id,
    required this.name,
    required this.assetTypeId,
    required this.currentLocationId,
    required this.currentLifecycleStateId,
    required this.currentCustodianId,
  });

  factory AssetSummary.fromJson(Map<String, dynamic> json) => AssetSummary(
        id: json['id'] as String,
        name: json['name'] as String,
        assetTypeId: json['asset_type_id'] as String,
        currentLocationId: json['current_location_id'] as String?,
        currentLifecycleStateId: json['current_lifecycle_state_id'] as String?,
        currentCustodianId: json['current_custodian_id'] as String?,
      );
}

/// Mirrors backend/app/tracking/schemas.py's TrackingEventRead.
class TrackingEventRead {
  final String id;
  final String assetId;
  final String providerType;
  final String eventType;
  final Map<String, dynamic> payload;
  final String? scannedBy;
  final DateTime occurredAt;

  TrackingEventRead({
    required this.id,
    required this.assetId,
    required this.providerType,
    required this.eventType,
    required this.payload,
    required this.scannedBy,
    required this.occurredAt,
  });

  factory TrackingEventRead.fromJson(Map<String, dynamic> json) => TrackingEventRead(
        id: json['id'] as String,
        assetId: json['asset_id'] as String,
        providerType: json['provider_type'] as String,
        eventType: json['event_type'] as String,
        payload: (json['payload'] as Map?)?.cast<String, dynamic>() ?? const {},
        scannedBy: json['scanned_by'] as String?,
        occurredAt: DateTime.parse(json['occurred_at'] as String),
      );
}

/// Mirrors backend/app/tracking/schemas.py's ScanResponse — the shape of
/// POST /tracking/scan's 201 `data` field.
class ScanResponse {
  final AssetSummary asset;
  final TrackingEventRead trackingEvent;

  ScanResponse({required this.asset, required this.trackingEvent});

  factory ScanResponse.fromJson(Map<String, dynamic> json) => ScanResponse(
        asset: AssetSummary.fromJson(json['asset'] as Map<String, dynamic>),
        trackingEvent: TrackingEventRead.fromJson(json['tracking_event'] as Map<String, dynamic>),
      );
}
