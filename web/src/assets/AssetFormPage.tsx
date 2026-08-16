import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PackageOpen } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useAssetTypes, useVendors } from "../catalog/hooks";
import { indentedLocationOptions, useAssetLocations } from "../locations/hooks";
import type { Asset, AssetCreateInput, AssetUpdateInput } from "./types";

export function AssetFormPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const isEdit = !!assetId;
  const { me } = useAuth();
  const requiredPermission = isEdit ? "assets.edit" : "assets.create";
  const hasPermission = me?.permissions.includes(requiredPermission) ?? false;

  const navigate = useNavigate();
  const { showToast } = useToast();

  const typesQuery = useAssetTypes();
  const vendorsQuery = useVendors();
  const locationsQuery = useAssetLocations();
  const hasTypes = (typesQuery.data?.length ?? 0) > 0;

  const assetQuery = useQuery({
    queryKey: ["assets", assetId],
    queryFn: () => api.get<Asset>(`/assets/${assetId}`),
    enabled: isEdit && hasPermission,
  });

  const [name, setName] = useState("");
  const [assetTypeId, setAssetTypeId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [purchaseOrderRef, setPurchaseOrderRef] = useState("");
  const [prefilled, setPrefilled] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (isEdit && assetQuery.data && !prefilled) {
      const a = assetQuery.data;
      setName(a.name);
      setAssetTypeId(a.asset_type_id);
      setVendorId(a.vendor_id ?? "");
      setPurchaseDate(a.purchase_date ?? "");
      setPurchasePrice(a.purchase_price ?? "");
      setPurchaseOrderRef(a.purchase_order_ref ?? "");
      setPrefilled(true);
    }
  }, [isEdit, assetQuery.data, prefilled]);

  const createAsset = useMutation({
    mutationFn: (body: AssetCreateInput) => api.post<Asset>("/assets", body),
    onSuccess: (asset) => {
      showToast("Asset created.", "success");
      navigate(`/assets/${asset.id}`, { replace: true });
    },
    onError: (err) => setFormError(apiErrorMessage(err, "Unable to create asset.")),
  });

  const updateAsset = useMutation({
    mutationFn: (body: AssetUpdateInput) => api.patch<Asset>(`/assets/${assetId}`, body),
    onSuccess: (asset) => {
      showToast("Asset updated.", "success");
      navigate(`/assets/${asset.id}`, { replace: true });
    },
    onError: (err) => setFormError(apiErrorMessage(err, "Unable to update asset.")),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (isEdit) {
      updateAsset.mutate({
        name: name.trim(),
        asset_type_id: assetTypeId,
        vendor_id: vendorId || null,
        purchase_date: purchaseDate || null,
        purchase_price: purchasePrice || null,
        purchase_order_ref: purchaseOrderRef.trim() || null,
      });
    } else {
      createAsset.mutate({
        name: name.trim(),
        asset_type_id: assetTypeId,
        current_location_id: locationId || undefined,
        vendor_id: vendorId || undefined,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice || undefined,
        purchase_order_ref: purchaseOrderRef.trim() || undefined,
      });
    }
  }

  if (!hasPermission) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <PackageOpen className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to {isEdit ? "edit" : "create"} assets</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  if (isEdit && assetQuery.isLoading) return <LoadingState />;
  if (isEdit && assetQuery.isError) {
    return <div className="text-sm text-red-600">{apiErrorMessage(assetQuery.error, "Unable to load asset.")}</div>;
  }

  const saving = createAsset.isPending || updateAsset.isPending;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{isEdit ? "Edit asset" : "New asset"}</h1>
      </div>

      {!typesQuery.isLoading && !hasTypes && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-3">
          There are no asset types yet. Go to Asset Catalog → Types to create one before registering an asset.
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}

        <div>
          <label htmlFor="asset-name" className="block text-sm font-medium text-slate-700 mb-1">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="asset-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="asset-type" className="block text-sm font-medium text-slate-700 mb-1">
            Type <span className="text-red-500">*</span>
          </label>
          <select
            id="asset-type"
            required
            disabled={!hasTypes}
            value={assetTypeId}
            onChange={(e) => setAssetTypeId(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">Select a type…</option>
            {typesQuery.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>

        {!isEdit && (
          <div>
            <label htmlFor="asset-location" className="block text-sm font-medium text-slate-700 mb-1">
              Initial location
            </label>
            <select id="asset-location" value={locationId} onChange={(e) => setLocationId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
              <option value="">No location</option>
              {indentedLocationOptions(locationsQuery.data ?? []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label htmlFor="asset-vendor" className="block text-sm font-medium text-slate-700 mb-1">
            Vendor
          </label>
          <select id="asset-vendor" value={vendorId} onChange={(e) => setVendorId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
            <option value="">No vendor</option>
            {vendorsQuery.data?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label htmlFor="purchase-date" className="block text-sm font-medium text-slate-700 mb-1">
              Purchase date
            </label>
            <input id="purchase-date" type="date" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label htmlFor="purchase-price" className="block text-sm font-medium text-slate-700 mb-1">
              Purchase price
            </label>
            <input
              id="purchase-price"
              type="number"
              step="0.01"
              value={purchasePrice}
              onChange={(e) => setPurchasePrice(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor="purchase-order-ref" className="block text-sm font-medium text-slate-700 mb-1">
              Purchase order ref
            </label>
            <input
              id="purchase-order-ref"
              value={purchaseOrderRef}
              onChange={(e) => setPurchaseOrderRef(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={saving || !hasTypes}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Create asset"}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
