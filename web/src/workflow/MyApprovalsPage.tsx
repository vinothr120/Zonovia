import { useState } from "react";
import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { StepStatusBadge } from "./InstancesListPage";
import { useApproveStep, useMyApprovals, useRejectStep } from "./hooks";
import type { ApprovalInstance, ApprovalInstanceStep } from "./types";

/** The most useful daily-use page in this module today — a pure client-derived filter over
 * GET /workflow/instances?status=pending (see useMyApprovals's docstring), no distinct
 * endpoint. Gated workflow.decide, same as the "My approvals" nav link — a Viewer could hold
 * workflow.view and reach this route directly, but could never act on anything shown here since
 * approve/reject both require workflow.decide server-side, so the page-level gate mirrors the
 * nav's rather than attempting a read-only rendering of someone else's queue. */
export function MyApprovalsPage() {
  const { me } = useAuth();
  const canDecide = me?.permissions.includes("workflow.decide") ?? false;
  const myApprovals = useMyApprovals();

  if (!canDecide) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <ShieldAlert className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to act on approvals</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">My approvals</h1>
        <p className="text-sm text-slate-500 mt-1">Approval steps currently waiting on you — by your user id or a role you hold.</p>
      </div>

      {myApprovals.isLoading && <LoadingState />}
      {myApprovals.isError && (
        <ErrorState message={apiErrorMessage(myApprovals.error, "Unable to load your approvals.")} onRetry={() => void myApprovals.refetch()} />
      )}

      {myApprovals.data && (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {myApprovals.rows.map(({ instance, step }) => (
            <ApprovalRow key={step.id} instance={instance} step={step} />
          ))}
          {myApprovals.rows.length === 0 && <EmptyState message="No approval steps are waiting on you right now." />}
        </div>
      )}
    </div>
  );
}

function ApprovalRow({ instance, step }: { instance: ApprovalInstance; step: ApprovalInstanceStep }) {
  const { showToast } = useToast();
  const approveStep = useApproveStep(step.id);
  const rejectStep = useRejectStep(step.id);
  const [error, setError] = useState<string | null>(null);

  // Both irreversible decisions with no undo path server-side — same window.confirm() tier as
  // Inventory/Maintenance's Complete/Cancel. There's no note/comment field: confirmed both
  // endpoints take no request body at all (router.py's approve_step/reject_step).
  function handleApprove() {
    if (!window.confirm("Approve this step? This can't be undone.")) return;
    setError(null);
    approveStep.mutate(undefined, {
      onSuccess: () => showToast("Step approved.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to approve this step.")),
    });
  }

  function handleReject() {
    if (!window.confirm("Reject this step? This rejects the entire approval request and can't be undone.")) return;
    setError(null);
    rejectStep.mutate(undefined, {
      onSuccess: () => showToast("Step rejected.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to reject this step.")),
    });
  }

  return (
    <div className="p-4 flex items-start justify-between gap-3 flex-wrap">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-900">
            {instance.entity_type} <span className="font-mono text-xs text-slate-500">{instance.entity_id}</span>
          </span>
          <StepStatusBadge status={step.status} />
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          Group {step.sequence_order} ·{" "}
          <Link to={`/workflow/instances/${instance.id}`} className="text-[var(--accent)] hover:underline">
            View instance
          </Link>
        </p>
        {error && <div className="text-red-600 text-xs mt-1">{error}</div>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          disabled={approveStep.isPending || rejectStep.isPending}
          onClick={handleApprove}
          className="text-sm border border-emerald-300 text-emerald-700 rounded-md px-3 py-1.5 hover:bg-emerald-50 disabled:opacity-60"
        >
          {approveStep.isPending ? "Approving…" : "Approve"}
        </button>
        <button
          type="button"
          disabled={approveStep.isPending || rejectStep.isPending}
          onClick={handleReject}
          className="text-sm border border-red-200 text-red-600 rounded-md px-3 py-1.5 hover:bg-red-50 disabled:opacity-60"
        >
          {rejectStep.isPending ? "Rejecting…" : "Reject"}
        </button>
      </div>
    </div>
  );
}
