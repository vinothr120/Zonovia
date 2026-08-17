// Hand-written to mirror backend/app/flow/schemas.py and FlowService.get_asset_history's
// return shape exactly (see flow/service.py).

export interface LifecycleState {
  id: string;
  key: string;
  label: string;
  is_initial: boolean;
  is_terminal: boolean;
  sort_order: number;
}

export interface LifecycleTransitionDefinition {
  id: string;
  from_state_id: string;
  to_state_id: string;
}

export interface AssetTransitionRequest {
  to_state_id: string;
  note?: string | null;
}

// Matches the raw dict router.transition_asset actually returns — NOT the
// AssetLifecycleTransitionRead Pydantic class (which additionally has transitioned_by).
export interface AssetTransitionResult {
  id: string;
  asset_id: string;
  from_state_id: string | null;
  to_state_id: string;
  transitioned_at: string;
  note: string | null;
}

export interface AssetAssignRequest {
  custodian_user_id: string;
  note?: string | null;
}

export interface AssetUnassignRequest {
  note?: string | null;
}

export interface AssetAssignmentResult {
  id: string;
  asset_id: string;
  custodian_user_id: string;
  assigned_at: string;
  unassigned_at: string | null;
  assigned_by: string | null;
  note: string | null;
}

export interface AssetMoveRequest {
  to_location_id: string;
  note?: string | null;
}

export interface AssetMovementResult {
  id: string;
  asset_id: string;
  from_location_id: string | null;
  to_location_id: string;
  moved_at: string;
  moved_by: string | null;
  note: string | null;
}

export interface LifecycleTransitionEntryData {
  id: string;
  from_state_id: string | null;
  to_state_id: string;
  transitioned_by: string | null;
  note: string | null;
}

export interface AssignmentEntryData {
  custodian_user_id: string;
  assigned_at: string;
  unassigned_at: string | null;
  note: string | null;
}

export interface MovementEntryData {
  from_location_id: string | null;
  to_location_id: string;
  note: string | null;
}

export type AssetHistoryEntry =
  | { entry_type: "lifecycle_transition"; occurred_at: string; data: LifecycleTransitionEntryData }
  | { entry_type: "assignment"; occurred_at: string; data: AssignmentEntryData }
  | { entry_type: "movement"; occurred_at: string; data: MovementEntryData };
