import { Link } from "react-router-dom";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import type { Asset } from "../assets/types";
import { assetLabel, useAssetsLookup, useScheduleDueReport } from "./hooks";
import type { ServiceSchedule } from "./types";

/** Deliberately read-only — no inline record-service control here, to avoid duplicating that
 * mutation UI in two places (it lives on AssetScheduleSection); rows link to the asset page
 * instead. Overdue/Upcoming are server-sorted (next_due_at asc within each bucket) — rendered
 * in the order the API returns them, no client sort. */
export function SchedulesDueReportPage() {
  const reportQuery = useScheduleDueReport();
  const allSchedules = [...(reportQuery.data?.overdue ?? []), ...(reportQuery.data?.upcoming ?? [])];
  const assetsLookup = useAssetsLookup(allSchedules.map((s) => s.asset_id));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Schedules due</h1>
        <p className="text-sm text-slate-500 mt-1">Service schedules across the tenant's assets, split by overdue vs. upcoming.</p>
      </div>

      {reportQuery.isLoading && <LoadingState />}
      {reportQuery.isError && (
        <ErrorState message={apiErrorMessage(reportQuery.error, "Unable to load the schedules due report.")} onRetry={() => void reportQuery.refetch()} />
      )}

      {reportQuery.data && (
        <>
          <ReportGroup title="Overdue" schedules={reportQuery.data.overdue} assetsMap={assetsLookup.map} tone="overdue" />
          <ReportGroup title="Upcoming" schedules={reportQuery.data.upcoming} assetsMap={assetsLookup.map} tone="upcoming" />
        </>
      )}
    </div>
  );
}

function ReportGroup({
  title,
  schedules,
  assetsMap,
  tone,
}: {
  title: string;
  schedules: ServiceSchedule[];
  assetsMap: Map<string, Asset>;
  tone: "overdue" | "upcoming";
}) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">
        {title} ({schedules.length})
      </h2>
      {schedules.length === 0 ? (
        <EmptyState message="None." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {schedules.map((s) => (
            <li key={s.id} className="py-2 flex items-center justify-between gap-3 text-sm flex-wrap">
              <div>
                <Link to={`/assets/${s.asset_id}`} className="text-[var(--accent)] hover:underline font-medium">
                  {assetLabel(s.asset_id, assetsMap)}
                </Link>
                <span className="text-slate-500 ml-2">{s.name}</span>
              </div>
              <span
                className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${
                  tone === "overdue" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-700"
                }`}
              >
                due {s.next_due_at}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
