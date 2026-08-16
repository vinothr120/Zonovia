import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { indentedLocationOptions, useAssetLocations } from "./hooks";
import { LocationTree } from "./LocationTree";
import type { AssetLocation, AssetLocationInput } from "./types";

const NO_PARENT = "";

export function LocationsPage() {
  const { me } = useAuth();
  const canView = me?.permissions.includes("asset_locations.view") ?? false;
  const canManage = me?.permissions.includes("asset_locations.manage") ?? false;
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const locationsQuery = useAssetLocations();

  const [editingLocation, setEditingLocation] = useState<AssetLocation | null>(null);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState<string>(NO_PARENT);
  const [locationType, setLocationType] = useState("");
  const [sortOrder, setSortOrder] = useState("0");
  const [formError, setFormError] = useState<string | null>(null);

  function resetForm() {
    setEditingLocation(null);
    setName("");
    setParentId(NO_PARENT);
    setLocationType("");
    setSortOrder("0");
    setFormError(null);
  }

  function startEdit(location: AssetLocation) {
    setEditingLocation(location);
    setName(location.name);
    setParentId(location.parent_location_id ?? NO_PARENT);
    setLocationType(location.location_type ?? "");
    setSortOrder(String(location.sort_order));
    setFormError(null);
  }

  function startAddChild(parentLocationId: string) {
    setEditingLocation(null);
    setName("");
    setParentId(parentLocationId);
    setLocationType("");
    setSortOrder("0");
    setFormError(null);
  }

  const createLocation = useMutation({
    mutationFn: (body: AssetLocationInput) => api.post<AssetLocation>("/asset-locations", body),
    onSuccess: () => {
      resetForm();
      void queryClient.invalidateQueries({ queryKey: ["asset-locations"] });
      showToast("Location created.", "success");
    },
    onError: (err) => setFormError(apiErrorMessage(err, "Unable to create location.")),
  });

  const updateLocation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AssetLocationInput }) => api.patch<AssetLocation>(`/asset-locations/${id}`, body),
    onSuccess: () => {
      resetForm();
      void queryClient.invalidateQueries({ queryKey: ["asset-locations"] });
      showToast("Location updated.", "success");
    },
    onError: (err) => setFormError(apiErrorMessage(err, "Unable to update location.")),
  });

  const deleteLocation = useMutation({
    mutationFn: (id: string) => api.delete(`/asset-locations/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["asset-locations"] });
      showToast("Location deleted.", "success");
    },
    // Backend referential-integrity errors (still has children, or assets reference it)
    // surface straight from ApiError.message — no client-side pre-check.
    onError: (err) => showToast(apiErrorMessage(err, "Unable to delete location."), "error"),
  });

  function handleDelete(location: AssetLocation) {
    if (window.confirm(`Delete location "${location.name}"? This can't be undone.`)) {
      deleteLocation.mutate(location.id);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const body: AssetLocationInput = {
      name: name.trim(),
      parent_location_id: parentId || null,
      location_type: locationType.trim() || undefined,
      sort_order: Number(sortOrder) || 0,
    };
    if (editingLocation) {
      updateLocation.mutate({ id: editingLocation.id, body });
    } else {
      createLocation.mutate(body);
    }
  }

  // A location can't become its own descendant's parent — exclude the node being edited (and
  // its own subtree isn't filtered client-side; the backend is the source of truth on cycles,
  // this just keeps the obvious self-parent case out of the dropdown).
  const parentOptions = (locationsQuery.data ?? []).filter((l) => l.id !== editingLocation?.id);
  const indentedOptions = indentedLocationOptions(parentOptions);
  const saving = createLocation.isPending || updateLocation.isPending;

  if (!canView) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <h2 className="text-slate-900 font-semibold mb-1">You don't have access to locations</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Locations</h1>
        <p className="text-sm text-slate-500 mt-1">The physical hierarchy assets can be placed in.</p>
      </div>

      {canManage && (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 max-w-2xl">
          <h2 className="text-sm font-medium text-slate-700">{editingLocation ? `Edit "${editingLocation.name}"` : "Add location"}</h2>
          {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2">{formError}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input required placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={parentId} onChange={(e) => setParentId(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
              <option value={NO_PARENT}>No parent (root)</option>
              {indentedOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
            <input placeholder="Type (e.g. Building, Room)" value={locationType} onChange={(e) => setLocationType(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input type="number" placeholder="Sort order" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={saving} className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60">
              {saving ? "Saving…" : editingLocation ? "Save changes" : "Add location"}
            </button>
            {editingLocation && (
              <button type="button" onClick={resetForm} className="text-sm text-slate-500 px-2">
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      {locationsQuery.isLoading && <LoadingState />}
      {locationsQuery.isError && (
        <ErrorState message={apiErrorMessage(locationsQuery.error, "Unable to load locations.")} onRetry={() => void locationsQuery.refetch()} />
      )}

      {locationsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 p-3">
          <LocationTree locations={locationsQuery.data} canManage={canManage} onAddChild={startAddChild} onEdit={startEdit} onDelete={handleDelete} />
        </div>
      )}
    </div>
  );
}
