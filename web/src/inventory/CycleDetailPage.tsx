import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { Breadcrumb } from "../core/ui/Breadcrumb";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import { CountsFeed } from "./CountsFeed";
import { CycleStatusActions } from "./CycleStatusActions";
import { ReportSection } from "./ReportSection";
import { VerificationForm } from "./VerificationForm";
import { useInventoryCycle } from "./hooks";

// Orchestrator: fetches the cycle, computes the three permission flags, and renders Overview
// then CycleStatusActions/VerificationForm/CountsFeed/ReportSection in order — same
// structural pattern as AssetDetailPage's orchestrator + sibling-sections layout.
export function CycleDetailPage() {
  const { cycleId } = useParams<{ cycleId: string }>();
  const { me } = useAuth();
  const locationsQuery = useAssetLocations();

  const canManageCycles = me?.permissions.includes("inventory.manage_cycles") ?? false;
  const canVerify = me?.permissions.includes("inventory.verify") ?? false;
  const canReconcile = me?.permissions.includes("inventory.reconcile") ?? false;

  const cycleQuery = useInventoryCycle(cycleId);

  if (!cycleId) return null;
  if (cycleQuery.isLoading) return <LoadingState />;
  if (cycleQuery.isError) {
    return <ErrorState message={apiErrorMessage(cycleQuery.error, "Unable to load inventory cycle.")} onRetry={() => void cycleQuery.refetch()} />;
  }
  const cycle = cycleQuery.data;
  if (!cycle) return null;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/inventory" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to inventory cycles
        </Link>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-slate-900">{cycle.name}</h1>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Overview</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">Status</dt>
          <dd className="text-slate-900">{cycle.status.replace("_", " ")}</dd>
          <dt className="text-slate-500">Scope</dt>
          <dd>
            {cycle.root_location_id ? (
              <Breadcrumb segments={locationBreadcrumb(cycle.root_location_id, locationsQuery.map)} />
            ) : (
              <span className="text-slate-900">Entire tenant</span>
            )}
          </dd>
          <dt className="text-slate-500">Description</dt>
          <dd className="text-slate-900">{cycle.description ?? "—"}</dd>
          <dt className="text-slate-500">Started</dt>
          <dd className="text-slate-900">{cycle.started_at ? new Date(cycle.started_at).toLocaleString() : "—"}</dd>
          <dt className="text-slate-500">Completed</dt>
          <dd className="text-slate-900">{cycle.completed_at ? new Date(cycle.completed_at).toLocaleString() : "—"}</dd>
        </dl>
      </div>

      <CycleStatusActions cycle={cycle} canManageCycles={canManageCycles} />
      <VerificationForm cycle={cycle} canVerify={canVerify} />
      <CountsFeed cycleId={cycle.id} />
      <ReportSection cycle={cycle} canReconcile={canReconcile} />
    </div>
  );
}
