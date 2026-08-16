import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useLifecycleStates, useTransitionAsset, useTransitionDefinitions } from "../flow/hooks";
import type { LifecycleState } from "../flow/types";
import type { Asset } from "./types";

/** Computes valid next states from asset.current_lifecycle_state_id: an exact-edge lookup in
 * the transition allow-list if a state is set, else the is_initial states. Never hides the
 * control on empty — the caller always renders select + button, disabled with a specific
 * reason, so the reason for "no options" is always visible rather than looking broken. */
export function LifecycleActions({ asset, canTransition }: { asset: Asset; canTransition: boolean }) {
  const { showToast } = useToast();
  const statesQuery = useLifecycleStates();
  const transitionsQuery = useTransitionDefinitions();
  const transitionAsset = useTransitionAsset(asset.id);

  const [toStateId, setToStateId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const currentStateId = asset.current_lifecycle_state_id;
  const currentState = currentStateId ? statesQuery.map.get(currentStateId) : undefined;

  const validTargets = useMemo(() => {
    if (currentStateId) {
      return (transitionsQuery.byFromState.get(currentStateId) ?? [])
        .map((t) => statesQuery.map.get(t.to_state_id))
        .filter((s): s is LifecycleState => !!s);
    }
    return [...statesQuery.map.values()].filter((s) => s.is_initial);
  }, [currentStateId, transitionsQuery.byFromState, statesQuery.map]);

  if (!canTransition) return null;

  let disabledReason: string | null = null;
  if (currentState?.is_terminal) {
    disabledReason = "This asset is in a terminal state and cannot transition further.";
  } else if (validTargets.length === 0) {
    disabledReason = currentStateId
      ? "No further transitions are configured from this asset's current state."
      : "No initial lifecycle state is configured for this tenant.";
  }

  function handleTransition(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!toStateId) return;
    transitionAsset.mutate(
      { to_state_id: toStateId, note: note.trim() || undefined },
      {
        onSuccess: () => {
          setToStateId("");
          setNote("");
          setError(null);
          showToast("Asset transitioned.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to transition asset.")),
      },
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Lifecycle</h2>

      <div className="mb-3">
        {currentState ? (
          <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5">{currentState.label}</span>
        ) : (
          <span className="text-slate-400 text-sm">No lifecycle state</span>
        )}
      </div>

      {error && <div className="text-red-600 text-xs mb-2">{error}</div>}

      <form onSubmit={handleTransition} className="flex flex-wrap gap-2 items-center">
        <select
          value={toStateId}
          onChange={(e) => setToStateId(e.target.value)}
          disabled={!!disabledReason}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white disabled:opacity-60 disabled:bg-slate-50"
        >
          <option value="">Select target state…</option>
          {validTargets.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Note (optional)"
          disabled={!!disabledReason}
          className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:opacity-60 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={!!disabledReason || transitionAsset.isPending || !toStateId}
          className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
        >
          {transitionAsset.isPending ? "Transitioning…" : "Transition"}
        </button>
      </form>

      {disabledReason && <p className="text-xs text-slate-500 mt-2">{disabledReason}</p>}
    </div>
  );
}
