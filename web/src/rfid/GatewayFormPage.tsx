import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Copy, Radio } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { indentedLocationOptions, useAssetLocations } from "../locations/hooks";
import { useCreateGateway } from "./hooks";
import type { DeviceGatewayCreateResponse } from "./types";

/** Create flow swaps the form in-place for a reveal-once warning panel on success — no route
 * navigation — because the raw API key (DeviceGatewayCreateResponse.api_key) is returned
 * exactly once, ever: DeviceGatewayService.create_gateway's docstring (tracking/service.py:
 * 117-119) states it is never logged, never audited, never stored (only api_key_hash/
 * api_key_last4 persist), and there is no backend mechanism to retrieve it again after this
 * response. The panel's only exit is a required "I've copied this key" checkbox gating the Done
 * button, plus a beforeunload guard while it's showing, so a refresh or back-navigation can't
 * silently discard the only copy of the key. */
export function GatewayFormPage() {
  const { me } = useAuth();
  const canManageGateways = me?.permissions.includes("tracking.manage_gateways") ?? false;
  const navigate = useNavigate();
  const createGateway = useCreateGateway();
  const locationsQuery = useAssetLocations();

  const [name, setName] = useState("");
  const [locationId, setLocationId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<DeviceGatewayCreateResponse | null>(null);

  useEffect(() => {
    if (!created) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [created]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!name.trim()) return;
    createGateway.mutate(
      { name: name.trim(), location_id: locationId || undefined },
      {
        onSuccess: (response) => setCreated(response),
        onError: (err) => setFormError(apiErrorMessage(err, "Unable to create gateway.")),
      },
    );
  }

  if (!canManageGateways) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Radio className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to create device gateways</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  if (created) {
    return <RevealKeyPanel response={created} onDone={() => navigate("/rfid/gateways", { replace: true })} />;
  }

  return (
    <div className="space-y-6 max-w-md">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New device gateway</h1>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}
        <div>
          <label htmlFor="gateway-name" className="block text-sm font-medium text-slate-700 mb-1">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="gateway-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="gateway-location" className="block text-sm font-medium text-slate-700 mb-1">
            Location
          </label>
          <select
            id="gateway-location"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
          >
            <option value="">No location</option>
            {indentedLocationOptions(locationsQuery.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={createGateway.isPending || !name.trim()}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createGateway.isPending ? "Creating…" : "Create gateway"}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function RevealKeyPanel({ response, onDone }: { response: DeviceGatewayCreateResponse; onDone: () => void }) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(response.api_key);
      setCopied(true);
      showToast("API key copied to clipboard.", "success");
    } catch {
      showToast("Unable to copy automatically — select and copy the key manually.", "error");
    }
  }

  return (
    <div className="space-y-6 max-w-md">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Gateway created</h1>
        <p className="text-sm text-slate-500 mt-1">"{response.gateway.name}" is ready. Copy its API key now — it is shown only this once.</p>
      </div>

      <div className="rounded-lg border border-amber-300 bg-amber-50 p-5 space-y-4">
        <p className="text-sm text-amber-900 font-medium">
          This is the only time this key will ever be shown. Zonovia stores only a hash of it — if you lose it, revoke this gateway and create a
          new one.
        </p>

        <div className="flex items-center gap-2">
          <code className="flex-1 min-w-0 break-all rounded-md border border-amber-300 bg-white px-3 py-2 text-sm font-mono text-slate-900">
            {response.api_key}
          </code>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-white text-amber-900 text-sm font-medium px-3 py-2 hover:bg-amber-100"
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <label className="flex items-start gap-2 text-sm text-amber-900">
          <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} className="mt-0.5" />
          I've copied this key and understand it won't be shown again.
        </label>

        <button
          type="button"
          disabled={!acknowledged}
          onClick={onDone}
          className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
        >
          Done
        </button>
      </div>
    </div>
  );
}
