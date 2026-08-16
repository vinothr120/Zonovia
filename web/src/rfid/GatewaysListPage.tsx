import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Plus, Radio } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { useGatewayDevices, useGateways, useRegisterDevice, useRevokeGateway } from "./hooks";
import type { Device, DeviceGateway } from "./types";

/** Gateway/device management is Tenant-Admin-only end to end — GET /tracking/gateways itself
 * requires tracking.manage_gateways, with no separate *.view tier (see seed.py's comment on
 * the Tenant Admin bundle: "NOT tracking.manage_gateways/manage_devices — those are
 * Tenant-Admin-only"). There's nothing partial to show a Member/Viewer here, so the whole page
 * is gated with the same "you don't have permission" message TicketFormPage uses for its own
 * Tenant-Admin-only entry point, rather than attempting a silently-broken fetch. Per-row expand
 * shows devices + a register-device mini-form inline instead of a separate detail route —
 * gateway objects are simple enough that a full detail page would be empty scaffolding. */
export function GatewaysListPage() {
  const { me } = useAuth();
  const canManageGateways = me?.permissions.includes("tracking.manage_gateways") ?? false;
  // Distinct permission — GET/POST .../devices are gated on tracking.manage_devices, not
  // tracking.manage_gateways (see gateways_router.register_device/list_devices). Both are
  // Tenant-Admin-only and always granted together in this app's seeded roles, but a custom
  // tenant role could split them, so GatewayDevices below checks this separately rather than
  // assuming canManageGateways implies it.
  const canManageDevices = me?.permissions.includes("tracking.manage_devices") ?? false;
  const gatewaysQuery = useGateways();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!canManageGateways) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Radio className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to view device gateways</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  const sorted = [...(gatewaysQuery.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Device gateways</h1>
          <p className="text-sm text-slate-500 mt-1">RFID reader gateways registered to this tenant, and the devices behind each one.</p>
        </div>
        <Link
          to="/rfid/gateways/new"
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
        >
          <Plus className="w-4 h-4" />
          New gateway
        </Link>
      </div>

      {gatewaysQuery.isLoading && <LoadingState />}
      {gatewaysQuery.isError && (
        <ErrorState message={apiErrorMessage(gatewaysQuery.error, "Unable to load device gateways.")} onRetry={() => void gatewaysQuery.refetch()} />
      )}

      {gatewaysQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {sorted.map((g) => (
            <GatewayRow
              key={g.id}
              gateway={g}
              expanded={expandedId === g.id}
              onToggle={() => setExpandedId((id) => (id === g.id ? null : g.id))}
              canManageDevices={canManageDevices}
            />
          ))}
          {sorted.length === 0 && <EmptyState message="No device gateways yet." />}
        </div>
      )}
    </div>
  );
}

function GatewayRow({
  gateway,
  expanded,
  onToggle,
  canManageDevices,
}: {
  gateway: DeviceGateway;
  expanded: boolean;
  onToggle: () => void;
  canManageDevices: boolean;
}) {
  const { showToast } = useToast();
  const revokeGateway = useRevokeGateway();
  const [error, setError] = useState<string | null>(null);

  function handleRevoke() {
    if (!window.confirm(`Revoke gateway "${gateway.name}"? This can't be undone — the gateway will no longer be able to submit reads.`)) return;
    setError(null);
    revokeGateway.mutate(gateway.id, {
      onSuccess: () => showToast("Gateway revoked.", "success"),
      onError: (err) => setError(apiErrorMessage(err, "Unable to revoke gateway.")),
    });
  }

  return (
    <div className="p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button type="button" onClick={onToggle} className="flex items-center gap-2 text-left min-w-0">
          {expanded ? <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />}
          <span className="text-sm font-medium text-slate-900 truncate">{gateway.name}</span>
          <span
            className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 shrink-0 ${
              gateway.status === "revoked" ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
            }`}
          >
            {gateway.status}
          </span>
        </button>
        {gateway.status !== "revoked" && (
          <button
            type="button"
            disabled={revokeGateway.isPending}
            onClick={handleRevoke}
            className="text-sm border border-red-200 text-red-600 rounded-md px-3 py-1.5 hover:bg-red-50 disabled:opacity-60 shrink-0"
          >
            {revokeGateway.isPending ? "Revoking…" : "Revoke"}
          </button>
        )}
      </div>
      <p className="text-xs text-slate-500 mt-1 ml-6">
        Key ending {gateway.api_key_last4} · Created {new Date(gateway.created_at).toLocaleDateString()} · Last seen{" "}
        {gateway.last_seen_at ? new Date(gateway.last_seen_at).toLocaleString() : "never"}
      </p>
      {error && <div className="text-red-600 text-xs mt-2 ml-6">{error}</div>}
      {expanded && <GatewayDevices gatewayId={gateway.id} canManageDevices={canManageDevices} />}
    </div>
  );
}

function GatewayDevices({ gatewayId, canManageDevices }: { gatewayId: string; canManageDevices: boolean }) {
  const devicesQuery = useGatewayDevices(canManageDevices ? gatewayId : undefined);
  const registerDevice = useRegisterDevice(gatewayId);
  const { showToast } = useToast();

  const [deviceType, setDeviceType] = useState("RFID_READER");
  const [vendor, setVendor] = useState("");
  const [model, setModel] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!deviceType.trim()) return;
    registerDevice.mutate(
      {
        device_type: deviceType.trim(),
        vendor: vendor.trim() || undefined,
        model: model.trim() || undefined,
        serial_number: serialNumber.trim() || undefined,
      },
      {
        onSuccess: () => {
          setVendor("");
          setModel("");
          setSerialNumber("");
          showToast("Device registered.", "success");
        },
        onError: (err) => setError(apiErrorMessage(err, "Unable to register device.")),
      },
    );
  }

  if (!canManageDevices) {
    return (
      <div className="mt-3 ml-6 border-t border-slate-100 pt-3">
        <h3 className="text-xs font-medium text-slate-500 mb-2">Devices</h3>
        <p className="text-sm text-slate-500">You don't have permission to manage devices for this gateway.</p>
      </div>
    );
  }

  return (
    <div className="mt-3 ml-6 border-t border-slate-100 pt-3">
      <h3 className="text-xs font-medium text-slate-500 mb-2">Devices</h3>

      {devicesQuery.isLoading && <LoadingState />}
      {devicesQuery.isError && (
        <ErrorState message={apiErrorMessage(devicesQuery.error, "Unable to load devices.")} onRetry={() => void devicesQuery.refetch()} />
      )}

      {devicesQuery.data && (
        <ul className="divide-y divide-slate-100 mb-3">
          {devicesQuery.data.map((d) => (
            <DeviceRow key={d.id} device={d} />
          ))}
          {devicesQuery.data.length === 0 && <EmptyState message="No devices registered under this gateway yet." />}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 items-center">
        {error && <div className="w-full text-red-600 text-xs">{error}</div>}
        <input
          value={deviceType}
          onChange={(e) => setDeviceType(e.target.value)}
          placeholder="Device type"
          className="w-36 rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
        <input value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="Vendor" className="w-28 rounded-md border border-slate-300 px-2 py-1 text-xs" />
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model" className="w-28 rounded-md border border-slate-300 px-2 py-1 text-xs" />
        <input
          value={serialNumber}
          onChange={(e) => setSerialNumber(e.target.value)}
          placeholder="Serial number"
          className="w-32 rounded-md border border-slate-300 px-2 py-1 text-xs"
        />
        <button
          type="submit"
          disabled={registerDevice.isPending || !deviceType.trim()}
          className="text-xs bg-[var(--accent)] text-white rounded-md px-2 py-1 disabled:opacity-60"
        >
          {registerDevice.isPending ? "Registering…" : "Register device"}
        </button>
      </form>
    </div>
  );
}

function DeviceRow({ device }: { device: Device }) {
  return (
    <li className="py-2 text-sm flex items-center justify-between gap-3">
      <div>
        <span className="text-slate-900">{[device.vendor, device.model].filter(Boolean).join(" ") || device.device_type}</span>
        <span className="text-slate-500 ml-2 text-xs">{device.device_type}</span>
        {device.serial_number && <span className="text-slate-400 ml-2 text-xs font-mono">S/N {device.serial_number}</span>}
      </div>
      <span
        className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 shrink-0 ${
          device.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"
        }`}
      >
        {device.status}
      </span>
    </li>
  );
}
