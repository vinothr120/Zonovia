import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useCreateSchedule, useDeleteSchedule, useRecordService, useSchedules, useUpdateSchedule } from "./hooks";
import type { ServiceSchedule } from "./types";

/** No server-side ordering on the per-asset schedule list — sorted client-side by name.
 * next_due_at/is_overdue are rendered exactly as returned by the API, never recomputed here.
 * Create/edit/delete/record-service all live inline on this section — no separate schedule
 * pages exist this round. */
export function AssetScheduleSection({ assetId, canView, canManage }: { assetId: string; canView: boolean; canManage: boolean }) {
  const schedulesQuery = useSchedules(assetId);

  const sorted = useMemo(
    () => [...(schedulesQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [schedulesQuery.data],
  );

  if (!canView) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Service schedules</h2>
        <p className="text-sm text-slate-500">You don't have permission to view this asset's service schedules.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Service schedules</h2>

      {schedulesQuery.isLoading && <LoadingState />}
      {schedulesQuery.isError && (
        <ErrorState message={apiErrorMessage(schedulesQuery.error, "Unable to load service schedules.")} onRetry={() => void schedulesQuery.refetch()} />
      )}

      {schedulesQuery.data && (
        <ul className="divide-y divide-slate-100 mb-3">
          {sorted.map((s) => (
            <ScheduleRow key={s.id} assetId={assetId} schedule={s} canManage={canManage} />
          ))}
          {sorted.length === 0 && <EmptyState message="No service schedules yet." />}
        </ul>
      )}

      {canManage && <AddScheduleForm assetId={assetId} />}
    </div>
  );
}

function ScheduleRow({ assetId, schedule, canManage }: { assetId: string; schedule: ServiceSchedule; canManage: boolean }) {
  const { showToast } = useToast();
  const updateSchedule = useUpdateSchedule(assetId, schedule.id);
  const deleteSchedule = useDeleteSchedule(assetId);
  const recordService = useRecordService(assetId, schedule.id);

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(schedule.name);
  const [intervalDays, setIntervalDays] = useState(String(schedule.interval_days));
  const [editError, setEditError] = useState<string | null>(null);

  const [recordOpen, setRecordOpen] = useState(false);
  const [servicedAt, setServicedAt] = useState("");

  function handleEditSubmit(e: FormEvent) {
    e.preventDefault();
    setEditError(null);
    const days = Number(intervalDays);
    if (!name.trim() || !Number.isFinite(days) || days <= 0) {
      setEditError("Name is required and interval must be a positive number of days.");
      return;
    }
    updateSchedule.mutate(
      { name: name.trim(), interval_days: days },
      {
        onSuccess: () => {
          setEditing(false);
          showToast("Schedule updated.", "success");
        },
        onError: (err) => setEditError(apiErrorMessage(err, "Unable to update schedule.")),
      },
    );
  }

  function handleDelete() {
    if (!window.confirm(`Delete service schedule "${schedule.name}"? This can't be undone.`)) return;
    deleteSchedule.mutate(schedule.id, {
      onSuccess: () => showToast("Schedule deleted.", "success"),
      onError: (err) => showToast(apiErrorMessage(err, "Unable to delete schedule."), "error"),
    });
  }

  function handleRecordService(e: FormEvent) {
    e.preventDefault();
    // Blank date omitted from the request so the backend applies its own "defaults to today"
    // rule, rather than the client guessing at today's date.
    recordService.mutate(
      { serviced_at: servicedAt || undefined },
      {
        onSuccess: () => {
          setServicedAt("");
          setRecordOpen(false);
          showToast("Service recorded.", "success");
        },
        onError: (err) => showToast(apiErrorMessage(err, "Unable to record service."), "error"),
      },
    );
  }

  if (editing) {
    return (
      <li className="py-2 text-sm">
        <form onSubmit={handleEditSubmit} className="flex flex-wrap gap-2 items-center">
          {editError && <div className="w-full text-red-600 text-xs">{editError}</div>}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs min-w-[10rem]"
          />
          <input
            type="number"
            min={1}
            value={intervalDays}
            onChange={(e) => setIntervalDays(e.target.value)}
            className="w-24 rounded-md border border-slate-300 px-2 py-1 text-xs"
          />
          <button type="submit" disabled={updateSchedule.isPending} className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60">
            {updateSchedule.isPending ? "Saving…" : "Save"}
          </button>
          <button type="button" onClick={() => setEditing(false)} className="text-xs text-slate-500 px-2 py-1">
            Cancel
          </button>
        </form>
      </li>
    );
  }

  return (
    <li className="py-2 text-sm">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <span className="text-slate-900 font-medium">{schedule.name}</span>
          <span className="text-slate-500 ml-2">every {schedule.interval_days} days</span>
          {schedule.is_overdue && (
            <span className="ml-2 inline-flex items-center rounded-full bg-red-100 text-red-700 text-xs px-2 py-0.5">overdue</span>
          )}
        </div>
        {canManage && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setRecordOpen((o) => !o)}
              className="text-xs border border-slate-300 text-slate-700 rounded-md px-2 py-1 hover:bg-slate-50"
            >
              {recordOpen ? "Close" : "Record service"}
            </button>
            <button
              type="button"
              aria-label={`Edit schedule ${schedule.name}`}
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              type="button"
              aria-label={`Delete schedule ${schedule.name}`}
              disabled={deleteSchedule.isPending}
              onClick={handleDelete}
              className="p-1.5 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
      <p className="text-xs text-slate-500 mt-0.5">
        Last serviced: {schedule.last_serviced_at ?? "never"} · Next due: {schedule.next_due_at}
      </p>
      {recordOpen && canManage && (
        <form onSubmit={handleRecordService} className="flex flex-wrap gap-2 items-center mt-2 border-t border-slate-100 pt-2">
          <input type="date" value={servicedAt} onChange={(e) => setServicedAt(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1 text-xs" />
          <button type="submit" disabled={recordService.isPending} className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60">
            {recordService.isPending ? "Recording…" : "Record"}
          </button>
          <p className="w-full text-xs text-slate-500">Leave blank to use today's date.</p>
        </form>
      )}
    </li>
  );
}

function AddScheduleForm({ assetId }: { assetId: string }) {
  const { showToast } = useToast();
  const createSchedule = useCreateSchedule(assetId);
  const [name, setName] = useState("");
  const [intervalDays, setIntervalDays] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const days = Number(intervalDays);
    if (!name.trim() || !Number.isFinite(days) || days <= 0) {
      setError("Name is required and interval must be a positive number of days.");
      return;
    }
    createSchedule.mutate(
      { asset_id: assetId, name: name.trim(), interval_days: days },
      {
        onSuccess: () => {
          setName("");
          setIntervalDays("");
          setError(null);
          showToast("Schedule created.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to create schedule.")),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 items-center border-t border-slate-100 pt-3">
      {error && <div className="w-full text-red-600 text-xs">{error}</div>}
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Schedule name"
        className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      />
      <input
        type="number"
        min={1}
        value={intervalDays}
        onChange={(e) => setIntervalDays(e.target.value)}
        placeholder="Interval (days)"
        className="w-36 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      />
      <button
        type="submit"
        disabled={createSchedule.isPending || !name.trim() || !intervalDays}
        className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
      >
        {createSchedule.isPending ? "Adding…" : "Add schedule"}
      </button>
    </form>
  );
}
