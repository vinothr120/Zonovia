import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Pencil } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import { TicketApprovalSection } from "../workflow/TicketApprovalSection";
import { TicketStatusBadge } from "./AssetTicketsSection";
import { assetLabel, useAssetsLookup, useTicket, useUpdateTicket } from "./hooks";
import { TicketStatusActions } from "./TicketStatusActions";
import { TICKET_PRIORITIES } from "./types";
import type { TicketPriority } from "./types";

/** Edit is an inline toggle on this Overview card (not a separate /edit route) — because
 * update is hard-blocked once the ticket goes terminal, hiding the toggle once terminal
 * sidesteps ever needing to handle "the ticket went terminal after you navigated to /edit" as
 * a real error state. */
export function TicketDetailPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const { me } = useAuth();
  const canManageTickets = me?.permissions.includes("maintenance.manage_tickets") ?? false;
  const canViewWorkflow = me?.permissions.includes("workflow.view") ?? false;
  const { showToast } = useToast();
  const usersLookup = useUsersLookup();

  const ticketQuery = useTicket(ticketId);
  const assetsLookup = useAssetsLookup(ticketQuery.data ? [ticketQuery.data.asset_id] : []);
  const updateTicket = useUpdateTicket(ticketId ?? "");

  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [assignedTo, setAssignedTo] = useState("");
  const [cost, setCost] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  const ticket = ticketQuery.data;
  const isTerminal = ticket?.status === "completed" || ticket?.status === "cancelled";

  function startEditing() {
    if (!ticket) return;
    setTitle(ticket.title);
    setDescription(ticket.description ?? "");
    setPriority(ticket.priority ?? "");
    setAssignedTo(ticket.assigned_to ?? "");
    setCost(ticket.cost ?? "");
    setEditError(null);
    setEditing(true);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setEditError(null);
    if (!title.trim()) return;
    updateTicket.mutate(
      {
        title: title.trim(),
        description: description.trim() || undefined,
        priority: priority || undefined,
        assigned_to: assignedTo || undefined,
        cost: cost.trim() || undefined,
      },
      {
        onSuccess: () => {
          setEditing(false);
          showToast("Ticket updated.", "success");
        },
        onError: (err) => setEditError(apiErrorMessage(err, "Unable to update ticket.")),
      },
    );
  }

  if (!ticketId) return null;
  if (ticketQuery.isLoading) return <LoadingState />;
  if (ticketQuery.isError) {
    return <ErrorState message={apiErrorMessage(ticketQuery.error, "Unable to load ticket.")} onRetry={() => void ticketQuery.refetch()} />;
  }
  if (!ticket) return null;

  const users = usersLookup.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <Link to="/maintenance/tickets" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to maintenance tickets
        </Link>
      </div>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{ticket.title}</h1>
          <Link to={`/assets/${ticket.asset_id}`} className="text-sm text-[var(--accent)] hover:underline">
            {assetLabel(ticket.asset_id, assetsLookup.map)}
          </Link>
        </div>
        {canManageTickets && !isTerminal && !editing && (
          <button
            type="button"
            onClick={startEditing}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 text-slate-700 text-sm font-medium px-3 py-1.5 hover:bg-slate-50"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit
          </button>
        )}
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Overview</h2>

        {editing ? (
          <form onSubmit={handleSubmit} className="space-y-3">
            {editError && <div className="text-red-600 text-xs">{editError}</div>}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Title <span className="text-red-500">*</span>
              </label>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Priority</label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TicketPriority | "")}
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
                >
                  <option value="">No priority</option>
                  {TICKET_PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Cost</label>
                <input type="number" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Assigned to</label>
              {usersLookup.canViewUsers ? (
                <select value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white">
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.email}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-slate-500">You don't have permission to view users, so an assignee can't be selected here.</p>
              )}
            </div>
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={updateTicket.isPending || !title.trim()} className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60">
                {updateTicket.isPending ? "Saving…" : "Save changes"}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="text-sm text-slate-500 px-2">
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-slate-500">Status</dt>
            <dd>
              <TicketStatusBadge status={ticket.status} />
            </dd>
            <dt className="text-slate-500">Priority</dt>
            <dd className="text-slate-900">{ticket.priority ?? "—"}</dd>
            <dt className="text-slate-500">Description</dt>
            <dd className="text-slate-900">{ticket.description ?? "—"}</dd>
            <dt className="text-slate-500">Reported by</dt>
            <dd className="text-slate-900">{custodianLabel(ticket.reported_by, usersLookup.map)}</dd>
            <dt className="text-slate-500">Assigned to</dt>
            <dd className="text-slate-900">{custodianLabel(ticket.assigned_to, usersLookup.map)}</dd>
            <dt className="text-slate-500">Cost</dt>
            <dd className="text-slate-900">{ticket.cost ?? "—"}</dd>
            <dt className="text-slate-500">Resolved</dt>
            <dd className="text-slate-900">{ticket.resolved_at ? new Date(ticket.resolved_at).toLocaleString() : "—"}</dd>
            <dt className="text-slate-500">Resolution note</dt>
            <dd className="text-slate-900">{ticket.resolution_note ?? "—"}</dd>
            <dt className="text-slate-500">Created</dt>
            <dd className="text-slate-900">{new Date(ticket.created_at).toLocaleString()}</dd>
          </dl>
        )}
      </div>

      <TicketApprovalSection ticketId={ticketId} canView={canViewWorkflow} />

      <TicketStatusActions ticket={ticket} canManageTickets={canManageTickets} />
    </div>
  );
}
