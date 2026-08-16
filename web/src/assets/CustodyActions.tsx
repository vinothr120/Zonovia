import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Breadcrumb } from "../core/ui/Breadcrumb";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useAssignCustodian, useMoveAsset, useUnassignCustodian } from "../flow/hooks";
import { indentedLocationOptions, locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import type { Asset } from "./types";

/** Assign/unassign + move, grouped together as "who/where" state. Renders nothing (not an
 * explanatory box) when both permissions are absent — unlike HistoryFeed, there's no read-only
 * content of its own being withheld here, since Overview already shows the current custodian
 * and location regardless of these permissions. */
export function CustodyActions({ asset, canAssign, canMove }: { asset: Asset; canAssign: boolean; canMove: boolean }) {
  if (!canAssign && !canMove) return null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      {canAssign && <CustodianSection asset={asset} bordered={false} bottomPad={canMove} />}
      {canMove && <LocationSection asset={asset} bordered={canAssign} />}
    </div>
  );
}

function CustodianSection({ asset, bordered, bottomPad }: { asset: Asset; bordered: boolean; bottomPad: boolean }) {
  const { showToast } = useToast();
  const usersLookup = useUsersLookup();
  const assignCustodian = useAssignCustodian(asset.id);
  const unassignCustodian = useUnassignCustodian(asset.id);

  const [custodianId, setCustodianId] = useState("");
  const [assignError, setAssignError] = useState<string | null>(null);

  function handleAssign(e: FormEvent) {
    e.preventDefault();
    setAssignError(null);
    if (!custodianId) return;
    assignCustodian.mutate(
      { custodian_user_id: custodianId },
      {
        onSuccess: () => {
          setCustodianId("");
          setAssignError(null);
          showToast("Custodian assigned.", "success");
        },
        onError: (err) => setAssignError(apiErrorMessage(err, "Unable to assign custodian.")),
      },
    );
  }

  function handleUnassign() {
    unassignCustodian.mutate(
      {},
      {
        onSuccess: () => showToast("Custodian unassigned.", "success"),
        onError: (err) => showToast(apiErrorMessage(err, "Unable to unassign custodian."), "error"),
      },
    );
  }

  const users = usersLookup.data ?? [];

  return (
    <div className={`${bordered ? "border-t border-slate-100 pt-4" : ""} ${bottomPad ? "pb-4" : ""}`}>
      <h3 className="text-sm font-medium text-slate-700 mb-3">Custodian</h3>

      {asset.current_custodian_id ? (
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-slate-900">{custodianLabel(asset.current_custodian_id, usersLookup.map)}</span>
          <button
            type="button"
            disabled={unassignCustodian.isPending}
            onClick={handleUnassign}
            className="text-sm border border-slate-300 text-slate-700 rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-60 shrink-0"
          >
            {unassignCustodian.isPending ? "Unassigning…" : "Unassign"}
          </button>
        </div>
      ) : usersLookup.canViewUsers ? (
        <form onSubmit={handleAssign} className="flex flex-wrap gap-2 items-center">
          {assignError && <div className="w-full text-red-600 text-xs">{assignError}</div>}
          <select
            value={custodianId}
            onChange={(e) => setCustodianId(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white min-w-[12rem]"
          >
            <option value="">Select user…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.email}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={assignCustodian.isPending || !custodianId}
            className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
          >
            {assignCustodian.isPending ? "Assigning…" : "Assign"}
          </button>
          {users.length === 0 && <p className="w-full text-xs text-slate-500">No other users exist in this tenant yet.</p>}
        </form>
      ) : (
        <p className="text-sm text-slate-500">You don't have permission to view users, so a custodian can't be selected here.</p>
      )}
    </div>
  );
}

function LocationSection({ asset, bordered }: { asset: Asset; bordered: boolean }) {
  const { showToast } = useToast();
  const locationsQuery = useAssetLocations();
  const moveAsset = useMoveAsset(asset.id);

  const [locationId, setLocationId] = useState("");
  const [moveError, setMoveError] = useState<string | null>(null);

  const breadcrumbSegments = locationBreadcrumb(asset.current_location_id, locationsQuery.map);

  const options = useMemo(
    () => indentedLocationOptions(locationsQuery.data ?? []).filter((o) => o.id !== asset.current_location_id),
    [locationsQuery.data, asset.current_location_id],
  );

  function handleMove(e: FormEvent) {
    e.preventDefault();
    setMoveError(null);
    if (!locationId) return;
    moveAsset.mutate(
      { to_location_id: locationId },
      {
        onSuccess: () => {
          setLocationId("");
          setMoveError(null);
          showToast("Asset moved.", "success");
        },
        onError: (err) => setMoveError(apiErrorMessage(err, "Unable to move asset.")),
      },
    );
  }

  return (
    <div className={bordered ? "border-t border-slate-100 pt-4" : ""}>
      <h3 className="text-sm font-medium text-slate-700 mb-3">Location</h3>

      <div className="mb-3">
        <Breadcrumb segments={breadcrumbSegments} />
      </div>

      {moveError && <div className="text-red-600 text-xs mb-2">{moveError}</div>}

      <form onSubmit={handleMove} className="flex flex-wrap gap-2 items-center">
        <select
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
          disabled={options.length === 0}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white min-w-[12rem] disabled:opacity-60 disabled:bg-slate-50"
        >
          <option value="">Select location…</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={options.length === 0 || moveAsset.isPending || !locationId}
          className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60"
        >
          {moveAsset.isPending ? "Moving…" : "Move"}
        </button>
      </form>

      {options.length === 0 && <p className="text-xs text-slate-500 mt-2">No other locations are available to move this asset to.</p>}
    </div>
  );
}
