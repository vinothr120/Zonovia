import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRightLeft, MapPinned, UserRoundCog } from "lucide-react";
import { api } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useLifecycleStates } from "../flow/hooks";
import type { AssetHistoryEntry } from "../flow/types";
import { useAssetLocations } from "../locations/hooks";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import type { UserSummary } from "../users/hooks";
import { TransitionApprovalIndicator } from "../workflow/TransitionApprovalIndicator";

/** Purely a read-only chronological feed — no action buttons. Flow write actions
 * (transition/assign/move) are explicitly out of scope this increment; this component only
 * proves the read side of the integration, merging entries already produced elsewhere
 * (curl/Swagger for now) with names resolved via the shared reference-data lookup maps.
 * `canViewWorkflow` is separate from `canView` (asset_lifecycle.view vs workflow.view) — a user
 * can see lifecycle history without being able to see Workflow's approval status, or vice versa. */
export function HistoryFeed({ assetId, canView, canViewWorkflow }: { assetId: string; canView: boolean; canViewWorkflow: boolean }) {
  const historyQuery = useQuery({
    queryKey: ["asset-history", assetId],
    queryFn: () => api.get<AssetHistoryEntry[]>(`/assets/${assetId}/history`),
    enabled: canView,
  });

  const statesQuery = useLifecycleStates();
  const locationsQuery = useAssetLocations();
  const usersLookup = useUsersLookup();

  if (!canView) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">History</h2>
        <p className="text-sm text-slate-500">You don't have permission to view this asset's lifecycle history.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">History</h2>

      {historyQuery.isLoading && <LoadingState />}
      {historyQuery.isError && (
        <ErrorState message={apiErrorMessage(historyQuery.error, "Unable to load history.")} onRetry={() => void historyQuery.refetch()} />
      )}

      {historyQuery.data && historyQuery.data.length === 0 && <EmptyState message="No history yet." />}

      {historyQuery.data && historyQuery.data.length > 0 && (
        <ul className="space-y-3">
          {historyQuery.data.map((entry, i) => (
            <HistoryEntryRow
              key={i}
              entry={entry}
              statesMap={statesQuery.map}
              locationsMap={locationsQuery.map}
              usersMap={usersLookup.map}
              canViewWorkflow={canViewWorkflow}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function HistoryEntryRow({
  entry,
  statesMap,
  locationsMap,
  usersMap,
  canViewWorkflow,
}: {
  entry: AssetHistoryEntry;
  statesMap: Map<string, { label: string }>;
  locationsMap: Map<string, { name: string }>;
  usersMap: Map<string, UserSummary>;
  canViewWorkflow: boolean;
}) {
  const when = new Date(entry.occurred_at).toLocaleString();

  if (entry.entry_type === "lifecycle_transition") {
    const from = entry.data.from_state_id ? (statesMap.get(entry.data.from_state_id)?.label ?? "unknown state") : "initial state";
    const to = statesMap.get(entry.data.to_state_id)?.label ?? "unknown state";
    return (
      <HistoryRow icon={<ArrowRightLeft className="w-4 h-4 text-indigo-500" />} when={when}>
        <span className="text-slate-900">
          Lifecycle transition: <span className="font-medium">{from}</span> → <span className="font-medium">{to}</span>
          <TransitionApprovalIndicator transitionId={entry.data.id} canView={canViewWorkflow} />
        </span>
        <HistoryMeta by={entry.data.transitioned_by ? custodianLabel(entry.data.transitioned_by, usersMap) : null} note={entry.data.note} />
      </HistoryRow>
    );
  }

  if (entry.entry_type === "assignment") {
    const custodian = custodianLabel(entry.data.custodian_user_id, usersMap);
    return (
      <HistoryRow icon={<UserRoundCog className="w-4 h-4 text-emerald-600" />} when={when}>
        <span className="text-slate-900">
          Assigned to <span className="font-medium">{custodian}</span>
          {entry.data.unassigned_at && <span className="text-slate-500"> (unassigned {new Date(entry.data.unassigned_at).toLocaleString()})</span>}
        </span>
        <HistoryMeta note={entry.data.note} />
      </HistoryRow>
    );
  }

  // movement
  const from = entry.data.from_location_id ? (locationsMap.get(entry.data.from_location_id)?.name ?? "unknown location") : "unassigned";
  const to = locationsMap.get(entry.data.to_location_id)?.name ?? "unknown location";
  return (
    <HistoryRow icon={<MapPinned className="w-4 h-4 text-amber-600" />} when={when}>
      <span className="text-slate-900">
        Moved: <span className="font-medium">{from}</span> → <span className="font-medium">{to}</span>
      </span>
      <HistoryMeta note={entry.data.note} />
    </HistoryRow>
  );
}

function HistoryRow({ icon, when, children }: { icon: ReactNode; when: string; children: ReactNode }) {
  return (
    <li className="flex gap-3 text-sm">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="min-w-0 flex-1">
        {children}
        <p className="text-xs text-slate-400 mt-0.5">{when}</p>
      </div>
    </li>
  );
}

function HistoryMeta({ by, note }: { by?: string | null; note?: string | null }) {
  if (!by && !note) return null;
  return (
    <p className="text-xs text-slate-500 mt-0.5">
      {by && <>by {by}</>}
      {by && note && " · "}
      {note && <span className="italic">“{note}”</span>}
    </p>
  );
}
