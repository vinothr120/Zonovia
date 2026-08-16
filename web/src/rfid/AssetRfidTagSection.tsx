import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../core/apiClient";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useAssetTag, useRegisterTag } from "./hooks";
import { TAG_TYPES } from "./types";
import type { TagType } from "./types";

/** RFID tags are register-only (POST + GET, no PATCH/DELETE) — a 404 means "no tag registered
 * yet," not a page error, same convention as maintenance/AssetWarrantySection's warranty
 * upsert-or-404 handling, just with no edit path afterward since the backend exposes none. */
export function AssetRfidTagSection({ assetId, canView, canManage }: { assetId: string; canView: boolean; canManage: boolean }) {
  const tagQuery = useAssetTag(assetId);

  if (!canView) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">RFID tag</h2>
        <p className="text-sm text-slate-500">You don't have permission to view this asset's RFID tag.</p>
      </div>
    );
  }

  const is404 = tagQuery.isError && tagQuery.error instanceof ApiError && tagQuery.error.status === 404;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">RFID tag</h2>

      {tagQuery.isLoading && <LoadingState />}
      {tagQuery.isError && !is404 && (
        <ErrorState message={apiErrorMessage(tagQuery.error, "Unable to load RFID tag.")} onRetry={() => void tagQuery.refetch()} />
      )}

      {tagQuery.data && (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-slate-500">EPC</dt>
          <dd className="text-slate-900 font-mono">{tagQuery.data.epc}</dd>
          <dt className="text-slate-500">Type</dt>
          <dd className="text-slate-900">{tagQuery.data.tag_type}</dd>
          <dt className="text-slate-500">Last read</dt>
          <dd className="text-slate-900">{tagQuery.data.last_read_at ? new Date(tagQuery.data.last_read_at).toLocaleString() : "never"}</dd>
          <dt className="text-slate-500">Registered</dt>
          <dd className="text-slate-900">{new Date(tagQuery.data.created_at).toLocaleString()}</dd>
        </dl>
      )}

      {is404 && (canManage ? <RegisterTagForm assetId={assetId} /> : <p className="text-sm text-slate-500">No RFID tag registered for this asset.</p>)}
    </div>
  );
}

function RegisterTagForm({ assetId }: { assetId: string }) {
  const { showToast } = useToast();
  const registerTag = useRegisterTag();
  const [epc, setEpc] = useState("");
  const [tagType, setTagType] = useState<TagType>("passive");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!epc.trim()) return;
    registerTag.mutate(
      { asset_id: assetId, epc: epc.trim(), tag_type: tagType },
      {
        onSuccess: () => {
          setEpc("");
          showToast("RFID tag registered.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to register RFID tag.")),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 items-center">
      {error && <div className="w-full text-red-600 text-xs">{error}</div>}
      <input
        value={epc}
        onChange={(e) => setEpc(e.target.value)}
        placeholder="EPC"
        className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm font-mono"
      />
      <select
        value={tagType}
        onChange={(e) => setTagType(e.target.value as TagType)}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
      >
        {TAG_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={registerTag.isPending || !epc.trim()}
        className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
      >
        {registerTag.isPending ? "Registering…" : "Register tag"}
      </button>
    </form>
  );
}
