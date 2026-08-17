import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import { InstanceStatusBadge, StepStatusBadge } from "./InstancesListPage";
import { useCancelInstance, useInstance } from "./hooks";
import type { ApprovalInstanceStep } from "./types";

function approverLabel(step: ApprovalInstanceStep, usersMap: ReturnType<typeof useUsersLookup>["map"]) {
  if (step.approver_role_key) return `Role: ${step.approver_role_key}`;
  return `User: ${custodianLabel(step.approver_user_id, usersMap)}`;
}

/** Tenant-wide admin view of one ApprovalInstance's full step timeline. Cancel is gated
 * workflow.manage_definitions (router.py: "Admin-reserved — no self-service cancel-your-own-
 * request path this round") and only legal while status is "pending" — same "always render,
 * disabled-with-reason when illegal" convention as TicketStatusActions/CycleStatusActions,
 * and the one other window.confirm() this module allows besides Approve/Reject. */
export function InstanceDetailPage() {
  const { instanceId } = useParams<{ instanceId: string }>();
  const { me } = useAuth();
  const canManageDefinitions = me?.permissions.includes("workflow.manage_definitions") ?? false;
  const { showToast } = useToast();
  const usersLookup = useUsersLookup();

  const instanceQuery = useInstance(instanceId);
  const cancelInstance = useCancelInstance(instanceId ?? "");
  const [error, setError] = useState<string | null>(null);

  function handleCancel() {
    if (!window.confirm("Cancel this approval instance? This can't be undone.")) return;
    setError(null);
    cancelInstance.mutate(undefined, {
      onSuccess: () => showToast("Instance cancelled.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to cancel this instance.")),
    });
  }

  if (!instanceId) return null;
  if (instanceQuery.isLoading) return <LoadingState />;
  if (instanceQuery.isError) {
    return <ErrorState message={apiErrorMessage(instanceQuery.error, "Unable to load approval instance.")} onRetry={() => void instanceQuery.refetch()} />;
  }
  const instance = instanceQuery.data;
  if (!instance) return null;

  const canCancel = instance.status === "pending";

  return (
    <div className="space-y-6">
      <div>
        <Link to="/workflow/instances" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to approval instances
        </Link>
      </div>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{instance.entity_type}</h1>
          <p className="text-sm text-slate-500 font-mono">{instance.entity_id}</p>
        </div>
        <InstanceStatusBadge status={instance.status} />
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Overview</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">Current group</dt>
          <dd className="text-slate-900">{instance.current_sequence_order ?? "—"}</dd>
          <dt className="text-slate-500">Requested by</dt>
          <dd className="text-slate-900">{custodianLabel(instance.requested_by, usersLookup.map)}</dd>
          <dt className="text-slate-500">Created</dt>
          <dd className="text-slate-900">{new Date(instance.created_at).toLocaleString()}</dd>
          <dt className="text-slate-500">Resolved</dt>
          <dd className="text-slate-900">{instance.resolved_at ? new Date(instance.resolved_at).toLocaleString() : "—"}</dd>
          <dt className="text-slate-500">Context</dt>
          <dd className="text-slate-900 font-mono text-xs whitespace-pre-wrap break-all">
            {instance.context && Object.keys(instance.context).length > 0 ? JSON.stringify(instance.context, null, 2) : "—"}
          </dd>
        </dl>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Step timeline</h2>
        <ul className="divide-y divide-slate-100">
          {instance.steps.map((step) => (
            <li key={step.id} className="py-2 text-sm flex items-center justify-between gap-3 flex-wrap">
              <div>
                <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5 mr-2">group {step.sequence_order}</span>
                <span className="text-slate-900">{approverLabel(step, usersLookup.map)}</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                {step.decided_at && <span>{new Date(step.decided_at).toLocaleString()}</span>}
                <StepStatusBadge status={step.status} />
              </div>
            </li>
          ))}
        </ul>
      </div>

      {canManageDefinitions && (
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="text-sm font-medium text-slate-700 mb-3">Actions</h2>
          {error && <div className="text-red-600 text-xs mb-2">{error}</div>}
          <button
            type="button"
            disabled={!canCancel || cancelInstance.isPending}
            onClick={handleCancel}
            className="text-sm border border-red-200 text-red-600 rounded-md px-3 py-1.5 hover:bg-red-50 disabled:opacity-60 disabled:hover:bg-transparent"
          >
            {cancelInstance.isPending ? "Cancelling…" : "Cancel instance"}
          </button>
          {!canCancel && <p className="text-xs text-slate-500 mt-2">This instance is {instance.status} — only a pending instance can be cancelled.</p>}
        </div>
      )}
    </div>
  );
}
