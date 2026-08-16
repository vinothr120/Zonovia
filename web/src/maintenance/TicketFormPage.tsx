import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useUsersLookup } from "../users/hooks";
import type { Asset } from "../assets/types";
import { AssetPicker } from "./AssetPicker";
import { useCreateTicket, useSchedules } from "./hooks";
import { TICKET_PRIORITIES } from "./types";
import type { TicketPriority } from "./types";

/** Handles both ticket-creation entry points via an optional ?asset_id= query param — present
 * (from AssetTicketsSection's "New ticket" link): asset shown read-only, no picker; absent
 * (from TicketsListPage): AssetPicker is required. service_schedule_id options only populate
 * once an asset is resolved either way. */
export function TicketFormPage() {
  const { me } = useAuth();
  const canManageTickets = me?.permissions.includes("maintenance.manage_tickets") ?? false;
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [searchParams] = useSearchParams();
  const presetAssetId = searchParams.get("asset_id") ?? "";

  const usersLookup = useUsersLookup();
  const createTicket = useCreateTicket();

  const [assetId, setAssetId] = useState(presetAssetId);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [assignedTo, setAssignedTo] = useState("");
  const [cost, setCost] = useState("");
  const [serviceScheduleId, setServiceScheduleId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const presetAssetQuery = useQuery({
    queryKey: ["assets", presetAssetId],
    queryFn: () => api.get<Asset>(`/assets/${presetAssetId}`),
    enabled: !!presetAssetId,
  });
  const schedulesQuery = useSchedules(assetId || undefined);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!assetId || !title.trim()) return;
    createTicket.mutate(
      {
        asset_id: assetId,
        service_schedule_id: serviceScheduleId || undefined,
        title: title.trim(),
        description: description.trim() || undefined,
        priority: priority || undefined,
        assigned_to: assignedTo || undefined,
        cost: cost.trim() || undefined,
      },
      {
        onSuccess: (ticket) => {
          showToast("Ticket created.", "success");
          navigate(`/maintenance/tickets/${ticket.id}`, { replace: true });
        },
        onError: (err) => setFormError(apiErrorMessage(err, "Unable to create ticket.")),
      },
    );
  }

  if (!canManageTickets) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Wrench className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to create maintenance tickets</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  const users = usersLookup.data ?? [];

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New maintenance ticket</h1>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Asset <span className="text-red-500">*</span>
          </label>
          {presetAssetId ? (
            <div className="rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900">
              {presetAssetQuery.data ? (
                <Link to={`/assets/${presetAssetId}`} className="text-[var(--accent)] hover:underline">
                  {presetAssetQuery.data.name}
                </Link>
              ) : (
                "Loading…"
              )}
            </div>
          ) : (
            <AssetPicker value={assetId} onChange={setAssetId} />
          )}
        </div>

        <div>
          <label htmlFor="ticket-title" className="block text-sm font-medium text-slate-700 mb-1">
            Title <span className="text-red-500">*</span>
          </label>
          <input
            id="ticket-title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="ticket-description" className="block text-sm font-medium text-slate-700 mb-1">
            Description
          </label>
          <textarea
            id="ticket-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="ticket-priority" className="block text-sm font-medium text-slate-700 mb-1">
              Priority
            </label>
            <select
              id="ticket-priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as TicketPriority | "")}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
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
            <label htmlFor="ticket-cost" className="block text-sm font-medium text-slate-700 mb-1">
              Cost
            </label>
            <input
              id="ticket-cost"
              type="number"
              step="0.01"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div>
          <label htmlFor="ticket-assigned-to" className="block text-sm font-medium text-slate-700 mb-1">
            Assigned to
          </label>
          {usersLookup.canViewUsers ? (
            <select
              id="ticket-assigned-to"
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
            >
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

        {assetId && (schedulesQuery.data?.length ?? 0) > 0 && (
          <div>
            <label htmlFor="ticket-schedule" className="block text-sm font-medium text-slate-700 mb-1">
              Related service schedule
            </label>
            <select
              id="ticket-schedule"
              value={serviceScheduleId}
              onChange={(e) => setServiceScheduleId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
            >
              <option value="">None</option>
              {schedulesQuery.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={createTicket.isPending || !assetId || !title.trim()}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createTicket.isPending ? "Creating…" : "Create ticket"}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
