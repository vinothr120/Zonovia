import { useState } from "react";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useCancelTicket, useCompleteTicket, useStartTicket } from "./hooks";
import type { MaintenanceTicket } from "./types";

/** Buttons are always rendered, disabled-with-specific-reason when illegal — same "never
 * silently hide" convention CycleStatusActions established. Legality mirrors
 * MaintenanceService's own guard clauses exactly: start requires open; complete requires
 * in_progress; cancel requires open OR in_progress; update (the inline edit toggle on
 * TicketDetailPage) is blocked once terminal. Complete and Cancel are irreversible, so both get
 * a window.confirm(), the same deliberate deviation from the no-confirm convention Start
 * doesn't need — an accidental start can just be cancelled. */
export function TicketStatusActions({ ticket, canManageTickets }: { ticket: MaintenanceTicket; canManageTickets: boolean }) {
  const { showToast } = useToast();
  const startTicket = useStartTicket(ticket.id);
  const completeTicket = useCompleteTicket(ticket.id);
  const cancelTicket = useCancelTicket(ticket.id);
  const [resolutionNote, setResolutionNote] = useState("");
  const [cancelNote, setCancelNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!canManageTickets) return null;

  const canStart = ticket.status === "open";
  const canComplete = ticket.status === "in_progress";
  const canCancel = ticket.status === "open" || ticket.status === "in_progress";

  function handleStart() {
    setError(null);
    startTicket.mutate(undefined, {
      onSuccess: () => showToast("Ticket started.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to start ticket.")),
    });
  }

  function handleComplete() {
    if (!window.confirm("Complete this ticket? This can't be undone.")) return;
    setError(null);
    completeTicket.mutate(
      { resolution_note: resolutionNote.trim() || undefined },
      {
        onSuccess: () => {
          setResolutionNote("");
          showToast("Ticket completed.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to complete ticket.")),
      },
    );
  }

  function handleCancel() {
    if (!window.confirm("Cancel this ticket? This can't be undone.")) return;
    setError(null);
    cancelTicket.mutate(
      { note: cancelNote.trim() || undefined },
      {
        onSuccess: () => {
          setCancelNote("");
          showToast("Ticket cancelled.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to cancel ticket.")),
      },
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Status</h2>

      {error && <div className="text-red-600 text-xs mb-2">{error}</div>}

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            disabled={!canStart || startTicket.isPending}
            onClick={handleStart}
            className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
          >
            {startTicket.isPending ? "Starting…" : "Start"}
          </button>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            disabled={!canComplete || completeTicket.isPending}
            onClick={handleComplete}
            className="text-sm border border-emerald-300 text-emerald-700 rounded-md px-3 py-1.5 hover:bg-emerald-50 disabled:opacity-60 disabled:hover:bg-transparent"
          >
            {completeTicket.isPending ? "Completing…" : "Complete"}
          </button>
          {canComplete && (
            <input
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              placeholder="Resolution note (optional)"
              className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          )}
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            disabled={!canCancel || cancelTicket.isPending}
            onClick={handleCancel}
            className="text-sm border border-red-200 text-red-600 rounded-md px-3 py-1.5 hover:bg-red-50 disabled:opacity-60 disabled:hover:bg-transparent"
          >
            {cancelTicket.isPending ? "Cancelling…" : "Cancel"}
          </button>
          {canCancel && (
            <input
              value={cancelNote}
              onChange={(e) => setCancelNote(e.target.value)}
              placeholder="Cancellation note (optional)"
              className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          )}
        </div>
      </div>

      {!canStart && !canComplete && !canCancel && (
        <p className="text-xs text-slate-500 mt-3">This ticket is {ticket.status.replace("_", " ")} — no further status changes are possible.</p>
      )}
    </div>
  );
}
