import { useState } from "react";
import type { FormEvent } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import type { ApproverFields } from "./ApproverPicker";
import { ApproverPicker } from "./ApproverPicker";
import { useAddStep, useDeleteStep, useSteps, useUpdateStep } from "./hooks";
import type { ApprovalStepDefinition } from "./types";

/** Direct template: AssetScheduleSection's list+add/edit/delete-inline pattern, adapted for
 * ApprovalStepDefinition rows. GET .../steps is server-ordered sequence_order asc — no client
 * sort needed. Steps sharing a sequence_order run in parallel (the model's own docstring), so
 * rows are grouped visually by that number rather than re-derived into nested groups. */
export function StepsSection({ definitionId, canManage }: { definitionId: string; canManage: boolean }) {
  const stepsQuery = useSteps(definitionId);
  const usersLookup = useUsersLookup();

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Approval steps</h2>

      {stepsQuery.isLoading && <LoadingState />}
      {stepsQuery.isError && (
        <ErrorState message={apiErrorMessage(stepsQuery.error, "Unable to load approval steps.")} onRetry={() => void stepsQuery.refetch()} />
      )}

      {stepsQuery.data && (
        <ul className="divide-y divide-slate-100 mb-3">
          {stepsQuery.data.map((s) => (
            <StepRow key={s.id} definitionId={definitionId} step={s} canManage={canManage} usersMap={usersLookup.map} />
          ))}
          {stepsQuery.data.length === 0 && <EmptyState message="No approval steps yet." />}
        </ul>
      )}

      {canManage && <AddStepForm definitionId={definitionId} nextSequenceOrder={(stepsQuery.data?.length ?? 0) + 1} />}
    </div>
  );
}

function approverSummary(step: { approver_user_id: string | null; approver_role_key: string | null }, usersMap: ReturnType<typeof useUsersLookup>["map"]) {
  if (step.approver_role_key) return `Role: ${step.approver_role_key}`;
  return `User: ${custodianLabel(step.approver_user_id, usersMap)}`;
}

function StepRow({
  definitionId,
  step,
  canManage,
  usersMap,
}: {
  definitionId: string;
  step: ApprovalStepDefinition;
  canManage: boolean;
  usersMap: ReturnType<typeof useUsersLookup>["map"];
}) {
  const { showToast } = useToast();
  const updateStep = useUpdateStep(definitionId, step.id);
  const deleteStep = useDeleteStep(definitionId);

  const [editing, setEditing] = useState(false);
  const [sequenceOrder, setSequenceOrder] = useState(String(step.sequence_order));
  const [approver, setApprover] = useState<ApproverFields>({
    approver_user_id: step.approver_user_id,
    approver_role_key: step.approver_role_key,
  });
  const [editError, setEditError] = useState<string | null>(null);

  function startEditing() {
    setSequenceOrder(String(step.sequence_order));
    setApprover({ approver_user_id: step.approver_user_id, approver_role_key: step.approver_role_key });
    setEditError(null);
    setEditing(true);
  }

  function handleEditSubmit(e: FormEvent) {
    e.preventDefault();
    setEditError(null);
    const order = Number(sequenceOrder);
    if (!Number.isFinite(order)) {
      setEditError("Sequence order must be a number.");
      return;
    }
    if (!approver.approver_user_id && !approver.approver_role_key) {
      setEditError("Select an approver user or role.");
      return;
    }
    // Footgun fix: always send sequence_order + approver_user_id + approver_role_key together
    // (the unselected field as literal null, never omitted) — the backend requires the
    // approver pair be sent together whenever either changes, and this shape can't violate
    // that by construction.
    updateStep.mutate(
      { sequence_order: order, approver_user_id: approver.approver_user_id || null, approver_role_key: approver.approver_role_key || null },
      {
        onSuccess: () => {
          setEditing(false);
          showToast("Step updated.", "success");
        },
        onError: (err) => setEditError(apiErrorMessage(err, "Unable to update step.")),
      },
    );
  }

  function handleDelete() {
    deleteStep.mutate(step.id, {
      onSuccess: () => showToast("Step deleted.", "success"),
      onError: (err) => showToast(apiErrorMessage(err, "Unable to delete step — a definition needs at least one step."), "error"),
    });
  }

  if (editing) {
    return (
      <li className="py-2 text-sm">
        <form onSubmit={handleEditSubmit} className="space-y-2">
          {editError && <div className="text-red-600 text-xs">{editError}</div>}
          <div className="flex flex-wrap gap-2 items-center">
            <label className="text-xs text-slate-500">Sequence</label>
            <input
              type="number"
              value={sequenceOrder}
              onChange={(e) => setSequenceOrder(e.target.value)}
              className="w-20 rounded-md border border-slate-300 px-2 py-1 text-xs"
            />
          </div>
          <ApproverPicker value={approver} onChange={setApprover} />
          <div className="flex gap-2">
            <button type="submit" disabled={updateStep.isPending} className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60">
              {updateStep.isPending ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={() => setEditing(false)} className="text-xs text-slate-500 px-2 py-1">
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="py-2 text-sm flex items-center justify-between gap-3 flex-wrap">
      <div>
        <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5 mr-2">group {step.sequence_order}</span>
        <span className="text-slate-900">{approverSummary(step, usersMap)}</span>
      </div>
      {canManage && (
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            aria-label={`Edit step ${step.id}`}
            onClick={startEditing}
            className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            type="button"
            aria-label={`Delete step ${step.id}`}
            disabled={deleteStep.isPending}
            onClick={handleDelete}
            className="p-1.5 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      )}
    </li>
  );
}

function AddStepForm({ definitionId, nextSequenceOrder }: { definitionId: string; nextSequenceOrder: number }) {
  const { showToast } = useToast();
  const addStep = useAddStep(definitionId);
  const [sequenceOrder, setSequenceOrder] = useState(String(nextSequenceOrder));
  const [approver, setApprover] = useState<ApproverFields>({ approver_user_id: "", approver_role_key: null });
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const order = Number(sequenceOrder);
    if (!Number.isFinite(order)) {
      setError("Sequence order must be a number.");
      return;
    }
    if (!approver.approver_user_id && !approver.approver_role_key) {
      setError("Select an approver user or role.");
      return;
    }
    addStep.mutate(
      { sequence_order: order, approver_user_id: approver.approver_user_id || undefined, approver_role_key: approver.approver_role_key || undefined },
      {
        onSuccess: () => {
          setSequenceOrder(String(nextSequenceOrder + 1));
          setApprover({ approver_user_id: "", approver_role_key: null });
          showToast("Step added.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to add step.")),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-100 pt-3">
      {error && <div className="text-red-600 text-xs">{error}</div>}
      <div className="flex flex-wrap gap-2 items-center">
        <label className="text-xs text-slate-500">Sequence</label>
        <input
          type="number"
          value={sequenceOrder}
          onChange={(e) => setSequenceOrder(e.target.value)}
          className="w-20 rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
      </div>
      <ApproverPicker value={approver} onChange={setApprover} />
      <button
        type="submit"
        disabled={addStep.isPending}
        className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
      >
        {addStep.isPending ? "Adding…" : "Add step"}
      </button>
    </form>
  );
}
