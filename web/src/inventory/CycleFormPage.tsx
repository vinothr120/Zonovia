import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import { indentedLocationOptions, useAssetLocations } from "../locations/hooks";
import { useCreateCycle } from "./hooks";

const ENTIRE_TENANT = "";

// Create only — no edit endpoint exists on the backend (InventoryCycleCreate is the only
// write-shaped schema besides the lifecycle actions), so this page never runs in an "edit" mode.
export function CycleFormPage() {
  const { me } = useAuth();
  const canManageCycles = me?.permissions.includes("inventory.manage_cycles") ?? false;
  const navigate = useNavigate();
  const { showToast } = useToast();
  const locationsQuery = useAssetLocations();
  const createCycle = useCreateCycle();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scopeLocationId, setScopeLocationId] = useState(ENTIRE_TENANT);
  const [formError, setFormError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!name.trim()) return;
    createCycle.mutate(
      {
        name: name.trim(),
        description: description.trim() || undefined,
        root_location_id: scopeLocationId || undefined,
      },
      {
        onSuccess: (cycle) => {
          showToast("Inventory cycle created.", "success");
          navigate(`/inventory/${cycle.id}`, { replace: true });
        },
        onError: (err) => setFormError(apiErrorMessage(err, "Unable to create inventory cycle.")),
      },
    );
  }

  if (!canManageCycles) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <ClipboardList className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to create inventory cycles</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New inventory cycle</h1>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}

        <div>
          <label htmlFor="cycle-name" className="block text-sm font-medium text-slate-700 mb-1">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="cycle-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="cycle-description" className="block text-sm font-medium text-slate-700 mb-1">
            Description
          </label>
          <textarea
            id="cycle-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="cycle-scope" className="block text-sm font-medium text-slate-700 mb-1">
            Scope
          </label>
          <select
            id="cycle-scope"
            value={scopeLocationId}
            onChange={(e) => setScopeLocationId(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
          >
            <option value={ENTIRE_TENANT}>Entire tenant</option>
            {indentedLocationOptions(locationsQuery.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500 mt-1">
            Limits the cycle to this location plus everything beneath it. Leave as "Entire tenant" to expect every asset.
          </p>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={createCycle.isPending || !name.trim()}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createCycle.isPending ? "Creating…" : "Create cycle"}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
