import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Asset } from "../assets/types";
import { Breadcrumb } from "../core/ui/Breadcrumb";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import type { AssetLocation } from "../locations/types";
import { assetLabel, useAssetsLookup, useCycleReport, useReconciliations, useRecordReconciliation } from "./hooks";
import { RECONCILIATION_ACTION_TYPES } from "./types";
import type { InventoryCycle, ReconciliationAction, ReconciliationActionType } from "./types";

const ACTION_LABELS: Record<ReconciliationActionType, string> = {
  location_corrected: "Location corrected",
  marked_lost: "Marked lost",
  acknowledged: "Acknowledged",
  other: "Other",
};

/** Always rendered (unlike CycleStatusActions/VerificationForm) — inventory.view is enough to
 * read the report, so a Viewer sees the summary/missing/discrepancy lists with zero reconcile
 * controls, rather than the section disappearing entirely. Reconciliation is rendered inline,
 * per row, directly on the missing/discrepancy lists — not a separate page — since
 * reconciliation's own guards only key off cycle_id+asset_id, and prior reconciliations for a
 * row are shown as badges (the backend allows duplicates, so the UI doesn't block them either,
 * it just surfaces prior decisions). */
export function ReportSection({ cycle, canReconcile }: { cycle: InventoryCycle; canReconcile: boolean }) {
  const reportQuery = useCycleReport(cycle.id);
  const reconciliationsQuery = useReconciliations(cycle.id);
  const locationsQuery = useAssetLocations();

  const involvedIds = [
    ...(reportQuery.data?.missing_asset_ids ?? []),
    ...(reportQuery.data?.discrepancies.map((d) => d.asset_id) ?? []),
  ];
  const assetsLookup = useAssetsLookup(involvedIds);

  // Mirrors InventoryService.record_reconciliation's guard exactly (in_progress or completed).
  const canReconcileNow = cycle.status === "in_progress" || cycle.status === "completed";

  if (reportQuery.isLoading) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <LoadingState />
      </div>
    );
  }
  if (reportQuery.isError) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <ErrorState message={apiErrorMessage(reportQuery.error, "Unable to load the cycle report.")} onRetry={() => void reportQuery.refetch()} />
      </div>
    );
  }
  const report = reportQuery.data;
  if (!report) return null;

  const reconciliationsByAsset = new Map<string, ReconciliationAction[]>();
  for (const action of reconciliationsQuery.data ?? []) {
    const list = reconciliationsByAsset.get(action.asset_id) ?? [];
    list.push(action);
    reconciliationsByAsset.set(action.asset_id, list);
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Report</h2>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <SummaryStat label="Expected" value={report.expected_asset_ids.length} />
        <SummaryStat label="Verified" value={report.verified_asset_ids.length} />
        <SummaryStat label="Missing" value={report.missing_asset_ids.length} />
        <SummaryStat label="Discrepancies" value={report.discrepancies.length} />
      </dl>
      {cycle.status === "draft" && (
        <p className="text-xs text-slate-500 mb-4">
          This cycle hasn't started yet — every expected asset shows as unverified until verification begins.
        </p>
      )}

      <div className="mb-5">
        <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Missing ({report.missing_asset_ids.length})</h3>
        {report.missing_asset_ids.length === 0 ? (
          <p className="text-sm text-slate-400">None.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {report.missing_asset_ids.map((assetId) => (
              <ReportRow
                key={assetId}
                cycleId={cycle.id}
                assetId={assetId}
                assetsMap={assetsLookup.map}
                priorActions={reconciliationsByAsset.get(assetId) ?? []}
                canReconcile={canReconcile}
                canReconcileNow={canReconcileNow}
              />
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Discrepancies ({report.discrepancies.length})</h3>
        {report.discrepancies.length === 0 ? (
          <p className="text-sm text-slate-400">None.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {report.discrepancies.map((count) => (
              <ReportRow
                key={count.asset_id}
                cycleId={cycle.id}
                assetId={count.asset_id}
                assetsMap={assetsLookup.map}
                priorActions={reconciliationsByAsset.get(count.asset_id) ?? []}
                canReconcile={canReconcile}
                canReconcileNow={canReconcileNow}
                expectedLocationId={count.expected_location_id}
                foundLocationId={count.found_location_id}
                note={count.condition_note}
                locationsMap={locationsQuery.map}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-slate-50 border border-slate-200 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-lg font-semibold text-slate-900">{value}</dd>
    </div>
  );
}

function ReportRow({
  cycleId,
  assetId,
  assetsMap,
  priorActions,
  canReconcile,
  canReconcileNow,
  expectedLocationId,
  foundLocationId,
  note,
  locationsMap,
}: {
  cycleId: string;
  assetId: string;
  assetsMap: Map<string, Asset>;
  priorActions: ReconciliationAction[];
  canReconcile: boolean;
  canReconcileNow: boolean;
  expectedLocationId?: string | null;
  foundLocationId?: string | null;
  note?: string | null;
  locationsMap?: Map<string, AssetLocation>;
}) {
  const { showToast } = useToast();
  const recordReconciliation = useRecordReconciliation(cycleId);
  const [open, setOpen] = useState(false);
  const [actionType, setActionType] = useState<ReconciliationActionType>("acknowledged");
  const [reconcileNote, setReconcileNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const disabledReason = !canReconcileNow ? "Reconciliation isn't available for this cycle's current status." : null;
  const isDiscrepancyRow = locationsMap !== undefined;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    recordReconciliation.mutate(
      { asset_id: assetId, action_type: actionType, note: reconcileNote.trim() || undefined },
      {
        onSuccess: () => {
          setReconcileNote("");
          setActionType("acknowledged");
          setOpen(false);
          setError(null);
          showToast("Reconciliation recorded.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to record reconciliation.")),
      },
    );
  }

  return (
    <li className="py-2 text-sm">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <Link to={`/assets/${assetId}`} className="text-[var(--accent)] hover:underline font-medium">
          {assetLabel(assetId, assetsMap)}
        </Link>
        {canReconcile && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            disabled={!!disabledReason}
            className="text-xs border border-slate-300 text-slate-700 rounded-md px-2 py-1 hover:bg-slate-50 disabled:opacity-60"
          >
            {open ? "Close" : "Reconcile"}
          </button>
        )}
      </div>

      {isDiscrepancyRow && (
        <p className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-1">
          <span>expected</span>
          <Breadcrumb segments={locationBreadcrumb(expectedLocationId ?? null, locationsMap!)} />
          <span>· found</span>
          <Breadcrumb segments={locationBreadcrumb(foundLocationId ?? null, locationsMap!)} />
        </p>
      )}
      {note && <p className="text-xs italic text-slate-500 mt-0.5">"{note}"</p>}

      {priorActions.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {priorActions.map((a) => (
            <span
              key={a.id}
              title={new Date(a.resolved_at).toLocaleString()}
              className="inline-flex items-center rounded-full bg-slate-100 text-slate-600 text-xs px-2 py-0.5"
            >
              {ACTION_LABELS[a.action_type]}
            </span>
          ))}
        </div>
      )}

      {open && canReconcile && (
        <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 items-center mt-2 border-t border-slate-100 pt-2">
          {error && <div className="w-full text-red-600 text-xs">{error}</div>}
          <select
            value={actionType}
            onChange={(e) => setActionType(e.target.value as ReconciliationActionType)}
            disabled={!!disabledReason}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs bg-white disabled:opacity-60"
          >
            {RECONCILIATION_ACTION_TYPES.map((t) => (
              <option key={t} value={t}>
                {ACTION_LABELS[t]}
              </option>
            ))}
          </select>
          <input
            value={reconcileNote}
            onChange={(e) => setReconcileNote(e.target.value)}
            placeholder="Note (optional)"
            disabled={!!disabledReason}
            className="flex-1 min-w-[8rem] rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!!disabledReason || recordReconciliation.isPending}
            className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60"
          >
            {recordReconciliation.isPending ? "Saving…" : "Save"}
          </button>
          {disabledReason && <p className="w-full text-xs text-slate-500">{disabledReason}</p>}
        </form>
      )}
    </li>
  );
}
