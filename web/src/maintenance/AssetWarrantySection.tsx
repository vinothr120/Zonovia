import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Pencil } from "lucide-react";
import { ApiError } from "../core/apiClient";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useVendors } from "../catalog/hooks";
import type { Vendor } from "../catalog/types";
import { useUpsertWarranty, useWarranty } from "./hooks";
import type { Warranty } from "./types";

/** Warranty is upsert-only (GET/PUT, no POST/DELETE) — a 404 means "no warranty yet," not a
 * page error, so it renders the create form directly rather than ErrorState. is_expired/
 * days_remaining are rendered exactly as returned by the API, never recomputed here. */
export function AssetWarrantySection({ assetId, canView, canManage }: { assetId: string; canView: boolean; canManage: boolean }) {
  const warrantyQuery = useWarranty(assetId);
  const vendorsQuery = useVendors();
  const [editing, setEditing] = useState(false);

  if (!canView) {
    return (
      <Card title="Warranty">
        <p className="text-sm text-slate-500">You don't have permission to view this asset's warranty.</p>
      </Card>
    );
  }

  const is404 = warrantyQuery.isError && warrantyQuery.error instanceof ApiError && warrantyQuery.error.status === 404;

  let body: ReactNode = null;
  if (warrantyQuery.isLoading) {
    body = <LoadingState />;
  } else if (warrantyQuery.isError && !is404) {
    body = <ErrorState message={apiErrorMessage(warrantyQuery.error, "Unable to load warranty.")} onRetry={() => void warrantyQuery.refetch()} />;
  } else if (is404) {
    body = canManage ? (
      <WarrantyForm assetId={assetId} warranty={undefined} vendors={vendorsQuery.data ?? []} onDone={() => setEditing(false)} />
    ) : (
      <p className="text-sm text-slate-500">No warranty on record for this asset.</p>
    );
  } else if (warrantyQuery.data) {
    body =
      editing && canManage ? (
        <WarrantyForm assetId={assetId} warranty={warrantyQuery.data} vendors={vendorsQuery.data ?? []} onDone={() => setEditing(false)} />
      ) : (
        <WarrantyReadView warranty={warrantyQuery.data} vendorsMap={vendorsQuery.map} />
      );
  }

  return (
    <Card
      title="Warranty"
      action={
        canManage && warrantyQuery.data && !editing ? (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1 text-xs border border-slate-300 text-slate-700 rounded-md px-2 py-1 hover:bg-slate-50"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit
          </button>
        ) : null
      }
    >
      {body}
    </Card>
  );
}

function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-slate-700">{title}</h2>
        {action}
      </div>
      {children}
    </div>
  );
}

function WarrantyReadView({ warranty, vendorsMap }: { warranty: Warranty; vendorsMap: Map<string, Vendor> }) {
  return (
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
      <dt className="text-slate-500">Vendor</dt>
      <dd className="text-slate-900">{warranty.vendor_id ? (vendorsMap.get(warranty.vendor_id)?.name ?? "—") : "—"}</dd>
      <dt className="text-slate-500">Type</dt>
      <dd className="text-slate-900">{warranty.warranty_type ?? "—"}</dd>
      <dt className="text-slate-500">Coverage</dt>
      <dd className="text-slate-900">
        {warranty.start_date} → {warranty.end_date}
      </dd>
      <dt className="text-slate-500">Status</dt>
      <dd>
        <span
          className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${
            warranty.is_expired ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
          }`}
        >
          {warranty.is_expired ? "Expired" : `${warranty.days_remaining} days remaining`}
        </span>
      </dd>
      {warranty.terms && (
        <>
          <dt className="text-slate-500">Terms</dt>
          <dd className="text-slate-900 whitespace-pre-wrap">{warranty.terms}</dd>
        </>
      )}
    </dl>
  );
}

function WarrantyForm({
  assetId,
  warranty,
  vendors,
  onDone,
}: {
  assetId: string;
  warranty: Warranty | undefined;
  vendors: Vendor[];
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const upsertWarranty = useUpsertWarranty(assetId);

  const [vendorId, setVendorId] = useState(warranty?.vendor_id ?? "");
  const [warrantyType, setWarrantyType] = useState(warranty?.warranty_type ?? "");
  const [startDate, setStartDate] = useState(warranty?.start_date ?? "");
  const [endDate, setEndDate] = useState(warranty?.end_date ?? "");
  const [terms, setTerms] = useState(warranty?.terms ?? "");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!startDate || !endDate) {
      setError("Start date and end date are required.");
      return;
    }
    // Client pre-check, backstopped by the server's own end_date >= start_date validation.
    if (endDate < startDate) {
      setError("End date must be on or after the start date.");
      return;
    }
    upsertWarranty.mutate(
      {
        vendor_id: vendorId || undefined,
        warranty_type: warrantyType.trim() || undefined,
        start_date: startDate,
        end_date: endDate,
        terms: terms.trim() || undefined,
      },
      {
        onSuccess: () => {
          setError(null);
          showToast(warranty ? "Warranty updated." : "Warranty created.", "success");
          onDone();
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to save warranty.")),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <div className="text-red-600 text-xs">{error}</div>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Vendor</label>
          <select value={vendorId} onChange={(e) => setVendorId(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white">
            <option value="">No vendor</option>
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Warranty type</label>
          <input value={warrantyType} onChange={(e) => setWarrantyType(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            Start date <span className="text-red-500">*</span>
          </label>
          <input type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">
            End date <span className="text-red-500">*</span>
          </label>
          <input type="date" required value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Terms</label>
        <textarea value={terms} onChange={(e) => setTerms(e.target.value)} rows={2} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={upsertWarranty.isPending} className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60">
          {upsertWarranty.isPending ? "Saving…" : warranty ? "Save changes" : "Create warranty"}
        </button>
        {warranty && (
          <button type="button" onClick={onDone} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
