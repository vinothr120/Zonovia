import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { assetLabel, useAssetsLookup } from "../inventory/hooks";
import { AssetPicker } from "../maintenance/AssetPicker";
import { useRegisterTag, useTags } from "./hooks";
import { TAG_TYPES } from "./types";
import type { TagType } from "./types";

/** GET /rfid/tags returns a plain array with no `total` (same as GET /inventory/cycles) —
 * fixed at the default offset=0/limit=20, a real backend limitation surfaced here rather than
 * papered over, same convention as inventory/CyclesListPage. "Register tag" opens AssetPicker
 * to select the asset first (this is the tenant-wide entry point, unlike
 * AssetRfidTagSection's asset-scoped one), then the same register form. */
export function RfidTagsListPage() {
  const { me } = useAuth();
  const canManageTags = me?.permissions.includes("track_rfid.manage_tags") ?? false;
  const tagsQuery = useTags({});
  const assetsLookup = useAssetsLookup((tagsQuery.data ?? []).map((t) => t.asset_id));
  const [registering, setRegistering] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">RFID tags</h1>
          <p className="text-sm text-slate-500 mt-1">Tags registered across the tenant's assets.</p>
        </div>
        {canManageTags && !registering && (
          <button
            type="button"
            onClick={() => setRegistering(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            Register tag
          </button>
        )}
      </div>

      {registering && <RegisterTagPanel onDone={() => setRegistering(false)} />}

      {tagsQuery.isLoading && <LoadingState />}
      {tagsQuery.isError && <ErrorState message={apiErrorMessage(tagsQuery.error, "Unable to load RFID tags.")} onRetry={() => void tagsQuery.refetch()} />}

      {tagsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">EPC</th>
                <th className="px-4 py-2 font-medium">Asset</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Last read</th>
                <th className="px-4 py-2 font-medium">Registered</th>
              </tr>
            </thead>
            <tbody>
              {tagsQuery.data.map((t) => (
                <tr key={t.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2 font-mono text-slate-900">{t.epc}</td>
                  <td className="px-4 py-2">
                    <Link to={`/assets/${t.asset_id}`} className="text-[var(--accent)] hover:underline">
                      {assetLabel(t.asset_id, assetsLookup.map)}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600">{t.tag_type}</td>
                  <td className="px-4 py-2 text-slate-500">{t.last_read_at ? new Date(t.last_read_at).toLocaleString() : "never"}</td>
                  <td className="px-4 py-2 text-slate-500">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {tagsQuery.data.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message="No RFID tags registered yet." />
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

function RegisterTagPanel({ onDone }: { onDone: () => void }) {
  const { showToast } = useToast();
  const registerTag = useRegisterTag();
  const [assetId, setAssetId] = useState("");
  const [epc, setEpc] = useState("");
  const [tagType, setTagType] = useState<TagType>("passive");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!assetId || !epc.trim()) return;
    registerTag.mutate(
      { asset_id: assetId, epc: epc.trim(), tag_type: tagType },
      {
        onSuccess: () => {
          showToast("RFID tag registered.", "success");
          onDone();
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to register RFID tag.")),
      },
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Register RFID tag</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <div className="text-red-600 text-xs">{error}</div>}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            Asset <span className="text-red-500">*</span>
          </label>
          <AssetPicker value={assetId} onChange={setAssetId} />
        </div>
        <div className="flex flex-wrap gap-2 items-center">
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
        </div>
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={registerTag.isPending || !assetId || !epc.trim()}
            className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
          >
            {registerTag.isPending ? "Registering…" : "Register"}
          </button>
          <button type="button" onClick={onDone} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
