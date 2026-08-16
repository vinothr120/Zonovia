import { Breadcrumb } from "../core/ui/Breadcrumb";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import { assetLabel, useAssetsLookup, useCycleCounts } from "./hooks";

/** Purely a read-only, reverse-chronological feed of recorded verifications. Asset names are
 * resolved via useAssetsLookup — the one place per the design decisions where a name lookup
 * is worth the round trip, since it's read once per row, not once per keystroke like
 * VerificationForm's submit loop would be. */
export function CountsFeed({ cycleId }: { cycleId: string }) {
  const countsQuery = useCycleCounts(cycleId);
  const locationsQuery = useAssetLocations();
  const assetsLookup = useAssetsLookup(countsQuery.data?.map((c) => c.asset_id) ?? []);

  const sorted = countsQuery.data ? [...countsQuery.data].sort((a, b) => b.verified_at.localeCompare(a.verified_at)) : undefined;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Verifications</h2>

      {countsQuery.isLoading && <LoadingState />}
      {countsQuery.isError && (
        <ErrorState message={apiErrorMessage(countsQuery.error, "Unable to load verifications.")} onRetry={() => void countsQuery.refetch()} />
      )}

      {sorted && sorted.length === 0 && <EmptyState message="No verifications recorded yet." />}

      {sorted && sorted.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {sorted.map((count) => (
            <li key={count.id} className="py-2 text-sm">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="text-slate-900 font-medium">{assetLabel(count.asset_id, assetsLookup.map)}</span>
                {count.has_discrepancy ? (
                  <span className="inline-flex items-center rounded-full bg-amber-100 text-amber-800 text-xs px-2 py-0.5">Discrepancy</span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-emerald-100 text-emerald-700 text-xs px-2 py-0.5">Matched</span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-1">
                <span>{new Date(count.verified_at).toLocaleString()}</span>
                {count.has_discrepancy && (
                  <>
                    <span>· expected</span>
                    <Breadcrumb segments={locationBreadcrumb(count.expected_location_id, locationsQuery.map)} />
                    <span>· found</span>
                    <Breadcrumb segments={locationBreadcrumb(count.found_location_id, locationsQuery.map)} />
                  </>
                )}
              </p>
              {count.condition_note && <p className="text-xs italic text-slate-500 mt-0.5">"{count.condition_note}"</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
