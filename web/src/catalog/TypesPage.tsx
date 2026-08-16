import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useAssetCategories, useAssetTypes } from "./hooks";
import type { AssetType, AssetTypeInput } from "./types";

export function TypesPage() {
  const { me } = useAuth();
  const canManage = me?.permissions.includes("asset_catalog.manage") ?? false;
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const typesQuery = useAssetTypes();
  const categoriesQuery = useAssetCategories();
  const hasCategories = (categoriesQuery.data?.length ?? 0) > 0;

  const [categoryId, setCategoryId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const createType = useMutation({
    mutationFn: (body: AssetTypeInput) => api.post<AssetType>("/asset-types", body),
    onSuccess: () => {
      setName("");
      setDescription("");
      setCreateError(null);
      void queryClient.invalidateQueries({ queryKey: ["asset-types"] });
      showToast("Type created.", "success");
    },
    onError: (err) => setCreateError(apiErrorMessage(err, "Unable to create type.")),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    const resolvedCategoryId = categoryId || categoriesQuery.data?.[0]?.id;
    if (!resolvedCategoryId) return;
    createType.mutate({ category_id: resolvedCategoryId, name: name.trim(), description: description.trim() || undefined });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Asset types</h1>
        <p className="text-sm text-slate-500 mt-1">Each type belongs to a category and is what assets are actually created against.</p>
      </div>

      {canManage && !categoriesQuery.isLoading && !hasCategories && (
        <div className="rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-3">
          You need at least one category before you can create a type.{" "}
          <Link to="/catalog/categories" className="underline font-medium">
            Create a category
          </Link>{" "}
          first.
        </div>
      )}

      {canManage && hasCategories && (
        <form onSubmit={handleCreate} className="bg-white rounded-lg border border-slate-200 p-4 space-y-3 max-w-2xl">
          <h2 className="text-sm font-medium text-slate-700">Add type</h2>
          {createError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2">{createError}</div>}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <select
              value={categoryId || (categoriesQuery.data?.[0]?.id ?? "")}
              onChange={(e) => setCategoryId(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
            >
              {categoriesQuery.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <input required placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={createType.isPending}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60"
          >
            {createType.isPending ? "Adding…" : "Add type"}
          </button>
        </form>
      )}

      {typesQuery.isLoading && <LoadingState />}
      {typesQuery.isError && (
        <ErrorState message={apiErrorMessage(typesQuery.error, "Unable to load types.")} onRetry={() => void typesQuery.refetch()} />
      )}

      {typesQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 font-medium">Description</th>
                {canManage && <th className="px-4 py-2 font-medium"></th>}
              </tr>
            </thead>
            <tbody>
              {typesQuery.data.map((t) => (
                <TypeRow key={t.id} assetType={t} categories={categoriesQuery.data ?? []} canManage={canManage} />
              ))}
              {typesQuery.data.length === 0 && (
                <tr>
                  <td colSpan={canManage ? 4 : 3}>
                    <EmptyState message="No asset types yet." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TypeRow({
  assetType,
  categories,
  canManage,
}: {
  assetType: AssetType;
  categories: { id: string; name: string }[];
  canManage: boolean;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [editing, setEditing] = useState(false);
  const [categoryId, setCategoryId] = useState(assetType.category_id);
  const [name, setName] = useState(assetType.name);
  const [description, setDescription] = useState(assetType.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const categoryName = categories.find((c) => c.id === assetType.category_id)?.name ?? "—";

  const updateType = useMutation({
    mutationFn: (body: AssetTypeInput) => api.patch<AssetType>(`/asset-types/${assetType.id}`, body),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["asset-types"] });
      showToast("Type updated.", "success");
    },
    onError: (err) => setError(apiErrorMessage(err, "Unable to update type.")),
  });

  const deleteType = useMutation({
    mutationFn: () => api.delete(`/asset-types/${assetType.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["asset-types"] });
      showToast("Type deleted.", "success");
    },
    onError: (err) => showToast(apiErrorMessage(err, "Unable to delete type."), "error"),
  });

  function handleDelete() {
    if (window.confirm(`Delete type "${assetType.name}"? This can't be undone.`)) {
      deleteType.mutate();
    }
  }

  if (editing) {
    return (
      <tr className="border-b border-slate-100 last:border-0 align-top">
        <td className="px-4 py-2" colSpan={4}>
          <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center">
            {error && <div className="text-red-600 text-xs w-full">{error}</div>}
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm bg-white">
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <input value={name} onChange={(e) => setName(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description"
              className="rounded-md border border-slate-300 px-2 py-1 text-sm flex-1"
            />
            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                disabled={updateType.isPending}
                onClick={() => updateType.mutate({ category_id: categoryId, name: name.trim(), description: description.trim() || undefined })}
                className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60"
              >
                {updateType.isPending ? "Saving…" : "Save"}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="text-xs text-slate-500">
                Cancel
              </button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="px-4 py-2 text-slate-900">{assetType.name}</td>
      <td className="px-4 py-2 text-slate-500">{categoryName}</td>
      <td className="px-4 py-2 text-slate-500">{assetType.description || "—"}</td>
      {canManage && (
        <td className="px-4 py-2">
          <div className="flex gap-1 justify-end">
            <button type="button" aria-label="Edit type" onClick={() => setEditing(true)} className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              <Pencil className="w-4 h-4" />
            </button>
            <button type="button" aria-label="Delete type" onClick={handleDelete} className="p-1.5 rounded-md text-slate-500 hover:bg-red-50 hover:text-red-600">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </td>
      )}
    </tr>
  );
}
