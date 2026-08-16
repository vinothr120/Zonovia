// Hand-written to mirror backend/app/flow/schemas.py and FlowService.get_asset_history's
// return shape exactly (see flow/service.py). Read-only DTOs only — this increment builds no
// Flow write actions (transition/assign/move buttons), just the reference-data hook and the
// shapes needed to render a read-only history feed.

export interface LifecycleState {
  id: string;
  key: string;
  label: string;
  is_initial: boolean;
  is_terminal: boolean;
  sort_order: number;
}

export interface LifecycleTransitionEntryData {
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
