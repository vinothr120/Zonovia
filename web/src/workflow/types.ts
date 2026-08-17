// Hand-written to mirror backend/app/workflow/schemas.py exactly — no codegen in this project.

// Mirrors app.workflow.models._CONDITION_OPERATORS exactly. condition_value is compared with
// raw Python ==/>/etc. server-side (WorkflowService._condition_matches), so the operator list
// itself is fixed but the value's TYPE (string vs number vs boolean) genuinely changes whether
// gt/gte/lt/lte ever matches — see ConditionEditor's typed value input.
export type ConditionOperator = "eq" | "ne" | "gt" | "gte" | "lt" | "lte";
export const CONDITION_OPERATORS: ConditionOperator[] = ["eq", "ne", "gt", "gte", "lt", "lte"];

// Mirrors app.workflow.models._INSTANCE_STATUSES exactly.
export type InstanceStatus = "pending" | "approved" | "rejected" | "cancelled";

// Mirrors app.workflow.models._STEP_STATUSES exactly.
export type StepStatus = "pending" | "approved" | "rejected" | "skipped";

// Mirrors app.workflow.models._NOTIFICATION_TYPES exactly.
export type NotificationType = "approval_pending" | "approval_resolved";

// -- definitions ----------------------------------------------------------------------------

export interface WorkflowDefinition {
  id: string;
  entity_type: string;
  name: string;
  is_active: boolean;
  condition_attribute: string | null;
  condition_operator: ConditionOperator | null;
  condition_value: string | number | boolean | null;
  created_at: string;
}

// Mirrors ApprovalStepDefinitionCreate — used only inside WorkflowDefinitionCreateInput.steps,
// POST /workflow/definitions takes the whole array in one shot (no separate add-step calls
// during creation).
export interface ApprovalStepDefinitionCreateEntry {
  sequence_order: number;
  approver_user_id?: string | null;
  approver_role_key?: string | null;
}

export interface WorkflowDefinitionCreateInput {
  entity_type: string;
  name: string;
  is_active?: boolean;
  condition_attribute?: string | null;
  condition_operator?: ConditionOperator | null;
  condition_value?: string | number | boolean | null;
  steps: ApprovalStepDefinitionCreateEntry[];
}

// All three condition fields must be sent together or all omitted — validated server-side
// (WorkflowService._validate_condition_triple) and mirrored client-side by ConditionEditor.
export interface WorkflowDefinitionUpdateInput {
  name?: string;
  is_active?: boolean;
  condition_attribute?: string | null;
  condition_operator?: ConditionOperator | null;
  condition_value?: string | number | boolean | null;
}

// -- step definitions -------------------------------------------------------------------------

export interface ApprovalStepDefinition {
  id: string;
  workflow_definition_id: string;
  sequence_order: number;
  approver_user_id: string | null;
  approver_role_key: string | null;
  created_at: string;
}

export interface ApprovalStepDefinitionAddInput {
  sequence_order: number;
  approver_user_id?: string | null;
  approver_role_key?: string | null;
}

// Deliberately all-required (not the ambient "omitted = don't touch" PATCH shape) — the PATCH
// endpoint requires approver_user_id/approver_role_key be sent together whenever either changes
// (service.py's UNSET-sentinel logic, confirmed against router.py's model_fields_set read).
// StepsSection's save always submits all three fields together, unselected approver field as
// literal null, so this shape makes the "send together" rule impossible to violate by
// construction rather than something the UI has to remember to track.
export interface ApprovalStepDefinitionSaveInput {
  sequence_order: number;
  approver_user_id: string | null;
  approver_role_key: string | null;
}

// -- instances --------------------------------------------------------------------------------

export interface ApprovalInstanceStep {
  id: string;
  approval_instance_id: string;
  step_definition_id: string | null;
  sequence_order: number;
  approver_user_id: string | null;
  approver_role_key: string | null;
  status: StepStatus;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface ApprovalInstance {
  id: string;
  workflow_definition_id: string;
  entity_type: string;
  entity_id: string;
  status: InstanceStatus;
  current_sequence_order: number | null;
  context: Record<string, unknown> | null;
  requested_by: string | null;
  resolved_at: string | null;
  created_at: string;
  steps: ApprovalInstanceStep[];
}

export interface EvaluateInstanceInput {
  entity_type: string;
  entity_id: string;
  context?: Record<string, unknown>;
}

// -- notifications ----------------------------------------------------------------------------

export interface Notification {
  id: string;
  recipient_user_id: string;
  type: NotificationType;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

// -- roles (for ApproverPicker's role side) ------------------------------------------------------

// Mirrors app.users.schemas.RoleRead — GET /roles requires roles.view, which every seeded
// Tenant Admin role holds (the only role that can ever reach ApproverPicker, since it's only
// rendered on workflow.manage_definitions-gated surfaces).
export interface Role {
  id: string;
  name: string;
  is_system_role: boolean;
  grantable: boolean;
}
