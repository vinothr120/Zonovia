import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import type {
  ApprovalInstance,
  ApprovalInstanceStep,
  ApprovalStepDefinition,
  ApprovalStepDefinitionAddInput,
  ApprovalStepDefinitionSaveInput,
  EvaluateInstanceInput,
  Notification,
  Role,
  WorkflowDefinition,
  WorkflowDefinitionCreateInput,
  WorkflowDefinitionUpdateInput,
} from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

// -- definitions ----------------------------------------------------------------------------

export interface DefinitionFilters {
  entity_type?: string;
  is_active?: boolean;
  // Index signature so this is assignable to api.get's params type.
  [key: string]: string | boolean | undefined;
}

// GET /workflow/definitions is server-ordered created_at asc (WorkflowDefinitionRepository.
// list_filtered) — re-sorted client-side by name, more useful for a small tenant-configured
// rule list than insertion order.
export function useDefinitions(filters: DefinitionFilters = {}) {
  return useQuery({
    queryKey: ["workflow-definitions", filters],
    queryFn: () => api.get<WorkflowDefinition[]>("/workflow/definitions", filters),
  });
}

export function useDefinition(definitionId: string | undefined) {
  return useQuery({
    queryKey: ["workflow-definitions", definitionId],
    queryFn: () => api.get<WorkflowDefinition>(`/workflow/definitions/${definitionId}`),
    enabled: !!definitionId,
  });
}

function useDefinitionListInvalidation() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["workflow-definitions"] });
}

export function useCreateDefinition() {
  const invalidate = useDefinitionListInvalidation();
  return useMutation({
    mutationFn: (body: WorkflowDefinitionCreateInput) => api.post<WorkflowDefinition>("/workflow/definitions", body),
    onSuccess: invalidate,
  });
}

export function useUpdateDefinition(definitionId: string) {
  const invalidate = useDefinitionListInvalidation();
  return useMutation({
    mutationFn: (body: WorkflowDefinitionUpdateInput) => api.patch<WorkflowDefinition>(`/workflow/definitions/${definitionId}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteDefinition() {
  const invalidate = useDefinitionListInvalidation();
  return useMutation({
    mutationFn: (definitionId: string) => api.delete(`/workflow/definitions/${definitionId}`),
    onSuccess: invalidate,
  });
}

// -- step definitions -------------------------------------------------------------------------

// GET .../steps is server-ordered sequence_order asc (ApprovalStepDefinitionRepository.
// list_for_definition) — no client sort needed.
export function useSteps(definitionId: string | undefined) {
  return useQuery({
    queryKey: ["workflow-steps", definitionId],
    queryFn: () => api.get<ApprovalStepDefinition[]>(`/workflow/definitions/${definitionId}/steps`),
    enabled: !!definitionId,
  });
}

function useStepListInvalidation(definitionId: string) {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["workflow-steps", definitionId] });
}

export function useAddStep(definitionId: string) {
  const invalidate = useStepListInvalidation(definitionId);
  return useMutation({
    mutationFn: (body: ApprovalStepDefinitionAddInput) => api.post<ApprovalStepDefinition>(`/workflow/definitions/${definitionId}/steps`, body),
    onSuccess: invalidate,
  });
}

/** The PATCH-step footgun: approver_user_id/approver_role_key must be sent together whenever
 * either changes (service.py's UNSET-sentinel logic). ApprovalStepDefinitionSaveInput makes
 * both fields required (not optional), so every caller — including a sequence_order-only
 * reorder — sends all three fields together by construction, no "did the approver actually
 * change" tracking needed here. */
export function useUpdateStep(definitionId: string, stepId: string) {
  const invalidate = useStepListInvalidation(definitionId);
  return useMutation({
    mutationFn: (body: ApprovalStepDefinitionSaveInput) =>
      api.patch<ApprovalStepDefinition>(`/workflow/definitions/${definitionId}/steps/${stepId}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteStep(definitionId: string) {
  const invalidate = useStepListInvalidation(definitionId);
  return useMutation({
    mutationFn: (stepId: string) => api.delete(`/workflow/definitions/${definitionId}/steps/${stepId}`),
    onSuccess: invalidate,
  });
}

// -- roles (ApproverPicker's role side) ----------------------------------------------------------

// Unconditional — only ever rendered from workflow.manage_definitions-gated surfaces
// (StepsSection, DefinitionFormPage), and every seeded role holding manage_definitions
// (Tenant Admin) also holds roles.view, so there's no partial-permission case to degrade for
// here, unlike useUsersLookup's canViewUsers gate.
export function useRoles() {
  return useQuery({
    queryKey: ["roles-lookup"],
    queryFn: () => api.get<Role[]>("/roles"),
    staleTime: REFERENCE_STALE_TIME,
  });
}

// -- instances --------------------------------------------------------------------------------

export interface InstanceFilters {
  entity_type?: string;
  entity_id?: string;
  status?: string;
  // Index signature so this is assignable to api.get's params type.
  [key: string]: string | undefined;
}

// GET /workflow/instances is server-ordered created_at desc (ApprovalInstanceRepository.
// list_filtered) — no client sort needed.
export function useInstances(filters: InstanceFilters = {}) {
  return useQuery({
    queryKey: ["workflow-instances", filters],
    queryFn: () => api.get<ApprovalInstance[]>("/workflow/instances", filters),
  });
}

export function useInstance(instanceId: string | undefined) {
  return useQuery({
    queryKey: ["workflow-instances", instanceId],
    queryFn: () => api.get<ApprovalInstance>(`/workflow/instances/${instanceId}`),
    enabled: !!instanceId,
  });
}

function useInstanceListInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["workflow-instances"] });
    // Every mutation below can create a Notification for some user (an approver on
    // evaluate/advance, the requester on resolve) — same "one invalidation covers everything
    // it could have touched" convention as useTicketListInvalidation.
    void queryClient.invalidateQueries({ queryKey: ["workflow-notifications"] });
  };
}

/** POST /workflow/instances/evaluate — a manual admin/testing trigger (gated
 * workflow.manage_definitions, same as every other mutation endpoint in this module), not a
 * real business action; see EvaluateInstancePage. Returns null when nothing matched or an
 * instance was already open for this entity — the caller renders that explicitly rather than
 * treating it as a silent no-op. */
export function useEvaluateInstance() {
  const invalidate = useInstanceListInvalidation();
  return useMutation({
    mutationFn: (body: EvaluateInstanceInput) => api.post<ApprovalInstance | null>("/workflow/instances/evaluate", body),
    onSuccess: invalidate,
  });
}

export function useCancelInstance(instanceId: string) {
  const invalidate = useInstanceListInvalidation();
  return useMutation({
    mutationFn: () => api.post<ApprovalInstance>(`/workflow/instances/${instanceId}/cancel`),
    onSuccess: invalidate,
  });
}

// -- instance-step decisions --------------------------------------------------------------------

/** Router gate is broad (workflow.decide); the service independently checks the actor is the
 * step's actual assignee (by user id, or membership in the assigned role) and raises
 * PermissionDeniedError otherwise (WorkflowService._is_assignee) — surfaced via the mutation's
 * onError like any other API error, not pre-checked client-side. */
export function useApproveStep(instanceStepId: string) {
  const invalidate = useInstanceListInvalidation();
  return useMutation({
    mutationFn: () => api.post<ApprovalInstanceStep>(`/workflow/instance-steps/${instanceStepId}/approve`),
    onSuccess: invalidate,
  });
}

export function useRejectStep(instanceStepId: string) {
  const invalidate = useInstanceListInvalidation();
  return useMutation({
    mutationFn: () => api.post<ApprovalInstanceStep>(`/workflow/instance-steps/${instanceStepId}/reject`),
    onSuccess: invalidate,
  });
}

export interface MyApprovalRow {
  instance: ApprovalInstance;
  step: ApprovalInstanceStep;
}

/** No server-side "my pending steps" endpoint exists — GET /workflow/instances?status=pending
 * returns every tenant-wide pending instance to any workflow.view holder, so this is a pure
 * client-side derived filter over that list, not a distinct query. Resolution mirrors
 * WorkflowService._is_assignee exactly: a step is mine if I'm its direct approver_user_id, or I
 * hold the role named by its approver_role_key (me.roles[].role_name, populated from Role.name
 * — the same column _resolve_approver_user_ids compares against server-side) — and it must be
 * both the instance's current actionable group and still pending. */
export function useMyApprovals() {
  const { me } = useAuth();
  const instancesQuery = useInstances({ status: "pending" });

  const rows = useMemo<MyApprovalRow[]>(() => {
    if (!me) return [];
    const result: MyApprovalRow[] = [];
    for (const instance of instancesQuery.data ?? []) {
      for (const step of instance.steps) {
        const isCurrentGroup = step.sequence_order === instance.current_sequence_order;
        const isPending = step.status === "pending";
        const isMine = step.approver_user_id === me.id || me.roles.some((r) => r.role_name === step.approver_role_key);
        if (isCurrentGroup && isPending && isMine) result.push({ instance, step });
      }
    }
    return result;
  }, [instancesQuery.data, me]);

  return { ...instancesQuery, rows };
}

// -- notifications ----------------------------------------------------------------------------

export interface NotificationFilters {
  unread_only?: boolean;
  // Index signature so this is assignable to api.get's params type.
  [key: string]: boolean | undefined;
}

// GET /workflow/notifications is server-ordered created_at desc — no client sort needed.
// Auth-only, no permission gate (every authenticated user manages their own inbox), so this is
// safe to call unconditionally from NotificationsBell regardless of role.
export function useNotifications(filters: NotificationFilters = {}) {
  return useQuery({
    queryKey: ["workflow-notifications", filters],
    queryFn: () => api.get<Notification[]>("/workflow/notifications", filters),
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) => api.post<Notification>(`/workflow/notifications/${notificationId}/read`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workflow-notifications"] }),
  });
}
