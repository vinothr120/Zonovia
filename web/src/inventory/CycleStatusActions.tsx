import { useState } from "react";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useCancelCycle, useCompleteCycle, useStartCycle } from "./hooks";
import type { InventoryCycle } from "./types";

/** Buttons are always rendered, disabled-with-specific-reason when illegal — same "never
 * silently hide" convention LifecycleActions established. Legality mirrors
 * InventoryService's own guard clauses exactly: start requires draft; complete requires
 * in_progress; cancel requires draft OR in_progress (confirmed directly against
 * cancel_cycle — a freshly created, never-started cycle can still be cancelled). Complete and
 * Cancel are irreversible — no reopen/uncancel exists anywhere in the service — so both get a
 * window.confirm(), the one deliberate deviation from the Flow-actions no-confirm convention.
 * Start gets no confirm: an accidental start can just be cancelled. */
export function CycleStatusActions({ cycle, canManageCycles }: { cycle: InventoryCycle; canManageCycles: boolean }) {
  const { showToast } = useToast();
  const startCycle = useStartCycle(cycle.id);
  const completeCycle = useCompleteCycle(cycle.id);
  const cancelCycle = useCancelCycle(cycle.id);
  const [error, setError] = useState<string | null>(null);

  if (!canManageCycles) return null;

  const canStart = cycle.status === "draft";
  const canComplete = cycle.status === "in_progress";
  const canCancel = cycle.status === "draft" || cycle.status === "in_progress";

  function handleStart() {
    setError(null);
    startCycle.mutate(undefined, {
      onSuccess: () => showToast("Cycle started.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to start cycle.")),
    });
  }

  function handleComplete() {
    if (!window.confirm("Complete this inventory cycle? This can't be undone.")) return;
    setError(null);
    completeCycle.mutate(undefined, {
      onSuccess: () => showToast("Cycle completed.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to complete cycle.")),
    });
  }

  function handleCancel() {
    if (!window.confirm("Cancel this inventory cycle? This can't be undone.")) return;
    setError(null);
    cancelCycle.mutate(undefined, {
      onSuccess: () => showToast("Cycle cancelled.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to cancel cycle.")),
    });
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Status</h2>

      {error && <div className="text-red-600 text-xs mb-2">{error}</div>}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canStart || startCycle.isPending}
          onClick={handleStart}
          className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
        >
          {startCycle.isPending ? "Starting…" : "Start"}
        </button>
        <button
          type="button"
          disabled={!canComplete || completeCycle.isPending}
          onClick={handleComplete}
          className="text-sm border border-emerald-300 text-emerald-700 rounded-md px-3 py-1.5 hover:bg-emerald-50 disabled:opacity-60 disabled:hover:bg-transparent"
        >
          {completeCycle.isPending ? "Completing…" : "Complete"}
        </button>
        <button
          type="button"
          disabled={!canCancel || cancelCycle.isPending}
          onClick={handleCancel}
          className="text-sm border border-red-200 text-red-600 rounded-md px-3 py-1.5 hover:bg-red-50 disabled:opacity-60 disabled:hover:bg-transparent"
        >
          {cancelCycle.isPending ? "Cancelling…" : "Cancel"}
        </button>
      </div>

      {!canStart && !canComplete && !canCancel && (
        <p className="text-xs text-slate-500 mt-2">
          This cycle is {cycle.status} — no further status changes are possible.
        </p>
      )}
      {cycle.status === "draft" && <p className="text-xs text-slate-500 mt-2">Start the cycle to begin recording verifications.</p>}
      {cycle.status === "in_progress" && <p className="text-xs text-slate-500 mt-2">Completing or cancelling this cycle is irreversible.</p>}
    </div>
  );
}
