// Hand-written to mirror backend/app/inventory/schemas.py's Inventory*/Reconciliation*/
// CycleReport models exactly — no codegen in this project. identifier_type reuses
// IdentifierType from ../assets/types (the authoritative, backend-mirroring allow-list),
// NOT tracking/types.ts's stale, narrower one (see the module's implementation plan).

import type { IdentifierType } from "../assets/types";

export type InventoryCycleStatus = "draft" | "in_progress" | "completed" | "cancelled";

export interface InventoryCycle {
  id: string;
  name: string;
  description: string | null;
  root_location_id: string | null;
  status: InventoryCycleStatus;
  started_at: string | null;
  completed_at: string | null;
}

export interface InventoryCycleCreateInput {
  name: string;
  description?: string | null;
  root_location_id?: string | null;
}

export interface InventoryCount {
  id: string;
  cycle_id: string;
  asset_id: string;
  verified_by: string | null;
  verified_at: string;
  expected_location_id: string | null;
  found_location_id: string | null;
  has_discrepancy: boolean;
  condition_note: string | null;
  tracking_event_id: string | null;
}

// Body of POST .../counts — reuses TrackingService.record_scan for scan resolution, so
// identifier_type/value match ScanRequest's shape exactly.
export interface InventoryVerificationInput {
  identifier_type: IdentifierType;
  value: string;
  found_location_id?: string | null;
  note?: string | null;
}

// InventoryService.get_cycle_report's return shape — computed on demand, not stored.
export interface CycleReport {
  cycle_id: string;
  expected_asset_ids: string[];
  verified_asset_ids: string[];
  missing_asset_ids: string[];
  discrepancies: InventoryCount[];
}

// Mirrors app.inventory.models._RECONCILIATION_ACTION_TYPES exactly.
export type ReconciliationActionType = "location_corrected" | "marked_lost" | "acknowledged" | "other";

export const RECONCILIATION_ACTION_TYPES: ReconciliationActionType[] = [
  "location_corrected",
  "marked_lost",
  "acknowledged",
  "other",
];

export interface ReconciliationAction {
  id: string;
  cycle_id: string;
  asset_id: string;
  action_type: ReconciliationActionType;
  note: string | null;
  resolved_by: string | null;
  resolved_at: string;
}

export interface ReconciliationInput {
  asset_id: string;
  action_type: ReconciliationActionType;
  note?: string | null;
}
