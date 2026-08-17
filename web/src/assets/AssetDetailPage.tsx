import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useAssetCategories, useAssetTypes, useVendors } from "../catalog/hooks";
import { useLifecycleStates } from "../flow/hooks";
import { Breadcrumb } from "../core/ui/Breadcrumb";
import { locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import { AssetScheduleSection } from "../maintenance/AssetScheduleSection";
import { AssetTicketsSection } from "../maintenance/AssetTicketsSection";
import { AssetWarrantySection } from "../maintenance/AssetWarrantySection";
import { AssetRfidTagSection } from "../rfid/AssetRfidTagSection";
import { CustodyActions } from "./CustodyActions";
import { DocumentsSection } from "./DocumentsSection";
import { HistoryFeed } from "./HistoryFeed";
import { IdentifiersSection } from "./IdentifiersSection";
import { LifecycleActions } from "./LifecycleActions";
import type { Asset } from "./types";

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const canEdit = me?.permissions.includes("assets.edit") ?? false;
  const canDelete = me?.permissions.includes("assets.delete") ?? false;
  const canManageDocuments = me?.permissions.includes("assets.manage_documents") ?? false;
  const canViewHistory = me?.permissions.includes("asset_lifecycle.view") ?? false;
  const canTransition = me?.permissions.includes("assets.transition_lifecycle") ?? false;
  const canAssign = me?.permissions.includes("assets.assign") ?? false;
  const canMove = me?.permissions.includes("assets.move") ?? false;
  const canViewMaintenance = me?.permissions.includes("maintenance.view") ?? false;
  const canManageWarranty = me?.permissions.includes("maintenance.manage_warranty") ?? false;
  const canManageSchedules = me?.permissions.includes("maintenance.manage_schedules") ?? false;
  const canManageTickets = me?.permissions.includes("maintenance.manage_tickets") ?? false;
  const canViewRfid = me?.permissions.includes("track_rfid.view") ?? false;
  const canManageRfidTags = me?.permissions.includes("track_rfid.manage_tags") ?? false;
  const canViewWorkflow = me?.permissions.includes("workflow.view") ?? false;

  const assetQuery = useQuery({
    queryKey: ["assets", assetId],
    queryFn: () => api.get<Asset>(`/assets/${assetId}`),
    enabled: !!assetId,
  });

  const typesQuery = useAssetTypes();
  const categoriesQuery = useAssetCategories();
  const vendorsQuery = useVendors();
  const locationsQuery = useAssetLocations();
  const statesQuery = useLifecycleStates();
  const usersLookup = useUsersLookup();

  const deleteAsset = useMutation({
    mutationFn: () => api.delete(`/assets/${assetId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assets"] });
      showToast("Asset deleted.", "success");
      navigate("/assets", { replace: true });
    },
    onError: (err) => showToast(apiErrorMessage(err, "Unable to delete asset."), "error"),
  });

  function handleDelete() {
    if (assetQuery.data && window.confirm(`Delete asset "${assetQuery.data.name}"? This can't be undone.`)) {
      deleteAsset.mutate();
    }
  }

  if (!assetId) return null;
  if (assetQuery.isLoading) return <LoadingState />;
  if (assetQuery.isError) {
    return <ErrorState message={apiErrorMessage(assetQuery.error, "Unable to load asset.")} onRetry={() => void assetQuery.refetch()} />;
  }
  const asset = assetQuery.data;
  if (!asset) return null;

  const assetType = typesQuery.map.get(asset.asset_type_id);
  const category = assetType ? categoriesQuery.map.get(assetType.category_id) : undefined;
  const vendor = asset.vendor_id ? vendorsQuery.map.get(asset.vendor_id) : undefined;
  const lifecycleState = asset.current_lifecycle_state_id ? statesQuery.map.get(asset.current_lifecycle_state_id) : undefined;
  const breadcrumbSegments = locationBreadcrumb(asset.current_location_id, locationsQuery.map);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/assets" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to assets
        </Link>
      </div>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <h1 className="text-xl font-semibold text-slate-900">{asset.name}</h1>
        <div className="flex gap-2">
          {canEdit && (
            <Link
              to={`/assets/${asset.id}/edit`}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 text-slate-700 text-sm font-medium px-3 py-1.5 hover:bg-slate-50"
            >
              <Pencil className="w-3.5 h-3.5" />
              Edit
            </Link>
          )}
          {canDelete && (
            <button
              type="button"
              disabled={deleteAsset.isPending}
              onClick={handleDelete}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-200 text-red-600 text-sm font-medium px-3 py-1.5 hover:bg-red-50 disabled:opacity-60"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete
            </button>
          )}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Overview</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">Type</dt>
          <dd className="text-slate-900">{assetType?.name ?? "—"}</dd>
          <dt className="text-slate-500">Category</dt>
          <dd className="text-slate-900">{category?.name ?? "—"}</dd>
          <dt className="text-slate-500">Vendor</dt>
          <dd className="text-slate-900">{vendor?.name ?? "—"}</dd>
          <dt className="text-slate-500">Location</dt>
          <dd>
            <Breadcrumb segments={breadcrumbSegments} />
          </dd>
          <dt className="text-slate-500">Lifecycle state</dt>
          <dd>
            {lifecycleState ? (
              <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5">{lifecycleState.label}</span>
            ) : (
              <span className="text-slate-400">—</span>
            )}
          </dd>
          <dt className="text-slate-500">Custodian</dt>
          <dd className="text-slate-900">{custodianLabel(asset.current_custodian_id, usersLookup.map)}</dd>
          <dt className="text-slate-500">Purchase date</dt>
          <dd className="text-slate-900">{asset.purchase_date ?? "—"}</dd>
          <dt className="text-slate-500">Purchase price</dt>
          <dd className="text-slate-900">{asset.purchase_price ?? "—"}</dd>
          <dt className="text-slate-500">Purchase order ref</dt>
          <dd className="text-slate-900">{asset.purchase_order_ref ?? "—"}</dd>
          <dt className="text-slate-500">Created</dt>
          <dd className="text-slate-900">{new Date(asset.created_at).toLocaleString()}</dd>
        </dl>
      </div>

      <LifecycleActions asset={asset} canTransition={canTransition} />
      <CustodyActions asset={asset} canAssign={canAssign} canMove={canMove} />

      <IdentifiersSection assetId={asset.id} canEdit={canEdit} />
      <DocumentsSection assetId={asset.id} canManage={canManageDocuments} />
      <AssetRfidTagSection assetId={asset.id} canView={canViewRfid} canManage={canManageRfidTags} />
      <AssetWarrantySection assetId={asset.id} canView={canViewMaintenance} canManage={canManageWarranty} />
      <AssetScheduleSection assetId={asset.id} canView={canViewMaintenance} canManage={canManageSchedules} />
      <AssetTicketsSection assetId={asset.id} canView={canViewMaintenance} canManageTickets={canManageTickets} />
      <HistoryFeed assetId={asset.id} canView={canViewHistory} canViewWorkflow={canViewWorkflow} />
    </div>
  );
}
