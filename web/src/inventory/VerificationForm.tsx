import { useState } from "react";
import type { FormEvent } from "react";
import { IDENTIFIER_TYPES } from "../assets/types";
import type { IdentifierType } from "../assets/types";
import { apiErrorMessage } from "../core/ui/StateViews";
import { indentedLocationOptions, useAssetLocations } from "../locations/hooks";
import { useRecordVerification } from "./hooks";
import type { InventoryCount, InventoryCycle } from "./types";

const NO_OVERRIDE = "";

/** null if !canVerify — same convention as CycleStatusActions/LifecycleActions. Manual entry
 * only (identifier-type select + value + optional "found at" location override + note) — no
 * camera, consistent with every non-ScanPage form in this app. Success feedback is a RAW
 * confirmation, not a name lookup: an operator recording counts is working through a run of
 * codes back-to-back, and a name-resolution round trip on every submit would add latency to
 * that loop for no decision-relevant benefit. Name resolution is instead spent where it's
 * actually read once, not once per keystroke — CountsFeed and ReportSection. */
export function VerificationForm({ cycle, canVerify }: { cycle: InventoryCycle; canVerify: boolean }) {
  const locationsQuery = useAssetLocations();
  const recordVerification = useRecordVerification(cycle.id);

  const [identifierType, setIdentifierType] = useState<IdentifierType>("QR");
  const [value, setValue] = useState("");
  const [foundLocationId, setFoundLocationId] = useState(NO_OVERRIDE);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<InventoryCount | null>(null);

  if (!canVerify) return null;

  const disabledReason =
    cycle.status !== "in_progress"
      ? `Verifications can only be recorded while a cycle is in progress (this cycle is ${cycle.status.replace("_", " ")}).`
      : null;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!value.trim()) return;
    recordVerification.mutate(
      {
        identifier_type: identifierType,
        value: value.trim(),
        found_location_id: foundLocationId || undefined,
        note: note.trim() || undefined,
      },
      {
        onSuccess: (count) => {
          setLastResult(count);
          setValue("");
          setFoundLocationId(NO_OVERRIDE);
          setNote("");
          setError(null);
        },
        onError: (err) => {
          setLastResult(null);
          setError(apiErrorMessage(err, "Unable to record verification."));
        },
      },
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Record verification</h2>

      {error && <div className="text-red-600 text-xs mb-2">{error}</div>}

      {lastResult && (
        <div
          className={`text-xs rounded-md px-3 py-2 mb-3 ${
            lastResult.has_discrepancy
              ? "bg-amber-50 border border-amber-200 text-amber-800"
              : "bg-emerald-50 border border-emerald-200 text-emerald-800"
          }`}
        >
          Recorded at {new Date(lastResult.verified_at).toLocaleTimeString()} —{" "}
          {lastResult.has_discrepancy ? "found at a different location than expected." : "no discrepancy."}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={identifierType}
            onChange={(e) => setIdentifierType(e.target.value as IdentifierType)}
            disabled={!!disabledReason}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white disabled:opacity-60 disabled:bg-slate-50"
          >
            {IDENTIFIER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Scanned / entered value"
            disabled={!!disabledReason}
            className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:opacity-60 disabled:bg-slate-50"
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={foundLocationId}
            onChange={(e) => setFoundLocationId(e.target.value)}
            disabled={!!disabledReason}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white min-w-[12rem] disabled:opacity-60 disabled:bg-slate-50"
          >
            <option value={NO_OVERRIDE}>Found at expected location</option>
            {indentedLocationOptions(locationsQuery.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            disabled={!!disabledReason}
            className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm disabled:opacity-60 disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={!!disabledReason || recordVerification.isPending || !value.trim()}
            className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
          >
            {recordVerification.isPending ? "Recording…" : "Record"}
          </button>
        </div>
      </form>

      {disabledReason && <p className="text-xs text-slate-500 mt-2">{disabledReason}</p>}
      {!disabledReason && (
        <p className="text-xs text-slate-400 mt-2">
          Only pick a "found at" location if it differs from where the asset is expected — leave it as-is to confirm the
          asset was found where expected.
        </p>
      )}
    </div>
  );
}
