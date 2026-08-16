import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { IDENTIFIER_TYPES } from "./types";
import type { AssetIdentifier, AssetIdentifierInput, IdentifierType } from "./types";

export function IdentifiersSection({ assetId, canEdit }: { assetId: string; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const queryKey = ["asset-identifiers", assetId];

  const identifiersQuery = useQuery({
    queryKey,
    queryFn: () => api.get<AssetIdentifier[]>(`/assets/${assetId}/identifiers`),
  });

  const [type, setType] = useState<IdentifierType>("QR");
  const [value, setValue] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const addIdentifier = useMutation({
    mutationFn: (body: AssetIdentifierInput) => api.post<AssetIdentifier>(`/assets/${assetId}/identifiers`, body),
    onSuccess: () => {
      setValue("");
      setIsPrimary(false);
      setAddError(null);
      void queryClient.invalidateQueries({ queryKey });
      showToast("Identifier added.", "success");
    },
    onError: (err) => setAddError(apiErrorMessage(err, "Unable to add identifier.")),
  });

  const removeIdentifier = useMutation({
    mutationFn: (identifierId: string) => api.delete(`/assets/${assetId}/identifiers/${identifierId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      showToast("Identifier removed.", "success");
    },
    onError: (err) => showToast(apiErrorMessage(err, "Unable to remove identifier."), "error"),
  });

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    setAddError(null);
    if (!value.trim()) return;
    addIdentifier.mutate({ identifier_type: type, value: value.trim(), is_primary: isPrimary });
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Identifiers</h2>

      {identifiersQuery.isLoading && <LoadingState />}
      {identifiersQuery.isError && (
        <ErrorState message={apiErrorMessage(identifiersQuery.error, "Unable to load identifiers.")} onRetry={() => void identifiersQuery.refetch()} />
      )}

      {identifiersQuery.data && (
        <ul className="divide-y divide-slate-100 mb-3">
          {identifiersQuery.data.map((id) => (
            <li key={id.id} className="py-2 flex items-center justify-between gap-3 text-sm">
              <div>
                <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5 mr-2">{id.identifier_type}</span>
                <span className="text-slate-900 font-mono">{id.value}</span>
                {id.is_primary && <span className="ml-2 text-xs text-[var(--accent)]">primary</span>}
              </div>
              {canEdit && (
                <button
                  type="button"
                  aria-label={`Remove identifier ${id.value}`}
                  disabled={removeIdentifier.isPending}
                  onClick={() => removeIdentifier.mutate(id.id)}
                  className="p-1.5 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600 shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </li>
          ))}
          {identifiersQuery.data.length === 0 && <EmptyState message="No identifiers yet." />}
        </ul>
      )}

      {canEdit && (
        <form onSubmit={handleAdd} className="flex flex-wrap gap-2 items-center border-t border-slate-100 pt-3">
          {addError && <div className="w-full text-red-600 text-xs">{addError}</div>}
          <select value={type} onChange={(e) => setType(e.target.value as IdentifierType)} className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white">
            {IDENTIFIER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Value"
            className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
            Primary
          </label>
          <button
            type="submit"
            disabled={addIdentifier.isPending || !value.trim()}
            className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
          >
            {addIdentifier.isPending ? "Adding…" : "Add"}
          </button>
        </form>
      )}
    </div>
  );
}
