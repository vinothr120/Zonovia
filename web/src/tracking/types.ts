// Re-exported from ../assets/types rather than redeclared here — this used to be its own
// "QR" | "BARCODE" union, which drifted stale once SERIAL/RFID_EPC were added there in Phase 6
// (the backend's _IDENTIFIER_TYPES allow-list is shared across every module, not tracking-specific).
export type { IdentifierType } from "../assets/types";
export { IDENTIFIER_TYPES } from "../assets/types";
import type { IdentifierType } from "../assets/types";

export interface ScanRequest {
  identifier_type: IdentifierType;
  value: string;
  note?: string;
}

/** Small DTO — enough to show what was scanned without a second round trip. */
export interface AssetSummary {
  id: string;
  name: string;
  asset_type_id: string;
  current_location_id: string | null;
  current_lifecycle_state_id: string | null;
  current_custodian_id: string | null;
}

export interface TrackingEvent {
  id: string;
  occurred_at: string;
  asset_id: string;
  provider_type: string;
  event_type: string;
  payload: Record<string, unknown>;
  scanned_by: string | null;
}

export interface ScanResponse {
  asset: AssetSummary;
  tracking_event: TrackingEvent;
}
