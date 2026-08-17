import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2, Workflow } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import type { ApproverFields } from "./ApproverPicker";
import { ApproverPicker } from "./ApproverPicker";
import type { ConditionFields } from "./ConditionEditor";
import { ConditionEditor } from "./ConditionEditor";
import { useCreateDefinition } from "./hooks";

interface LocalStepRow extends ApproverFields {
  key: number;
  sequence_order: string;
}

let nextRowKey = 0;
function newRow(sequenceOrder: number): LocalStepRow {
  return { key: nextRowKey++, sequence_order: String(sequenceOrder), approver_user_id: "", approver_role_key: null };
}

/** Tenant-Admin-only end to end (workflow.manage_definitions), same permission-message pattern
 * as RFID's GatewayFormPage — there's nothing partial to show anyone else here. Step rows are
 * local-only state, not persisted individually, because POST /workflow/definitions takes the
 * whole `steps` array in one shot (WorkflowService.create_definition) — unlike
 * DefinitionDetailPage's StepsSection, which edits an already-created definition's steps one at
 * a time via their own endpoints. */
export function DefinitionFormPage() {
  const { me } = useAuth();
  const canManageDefinitions = me?.permissions.includes("workflow.manage_definitions") ?? false;
  const navigate = useNavigate();
  const { showToast } = useToast();
  const createDefinition = useCreateDefinition();

  const [entityType, setEntityType] = useState("");
  const [name, setName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [condition, setCondition] = useState<ConditionFields>({ condition_attribute: null, condition_operator: null, condition_value: null });
  const [rows, setRows] = useState<LocalStepRow[]>([newRow(1)]);
  const [formError, setFormError] = useState<string | null>(null);

  function updateRow(key: number, next: ApproverFields) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...next } : r)));
  }

  function updateRowSequence(key: number, sequenceOrder: string) {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, sequence_order: sequenceOrder } : r)));
  }

  function addRow() {
    setRows((prev) => [...prev, newRow(prev.length + 1)]);
  }

  function removeRow(key: number) {
    setRows((prev) => prev.filter((r) => r.key !== key));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!entityType.trim() || !name.trim()) return;
    if (rows.length === 0) {
      setFormError("A workflow definition needs at least one approval step.");
      return;
    }
    const steps: { sequence_order: number; approver_user_id: string | null; approver_role_key: string | null }[] = [];
    for (const row of rows) {
      const order = Number(row.sequence_order);
      if (!Number.isFinite(order)) {
        setFormError("Every step's sequence order must be a number.");
        return;
      }
      if (!row.approver_user_id && !row.approver_role_key) {
        setFormError("Every step needs an approver user or role selected.");
        return;
      }
      steps.push({ sequence_order: order, approver_user_id: row.approver_user_id || null, approver_role_key: row.approver_role_key || null });
    }

    createDefinition.mutate(
      {
        entity_type: entityType.trim(),
        name: name.trim(),
        is_active: isActive,
        condition_attribute: condition.condition_attribute,
        condition_operator: condition.condition_operator,
        condition_value: condition.condition_value,
        steps,
      },
      {
        onSuccess: (definition) => {
          showToast("Workflow definition created.", "success");
          navigate(`/workflow/definitions/${definition.id}`, { replace: true });
        },
        onError: (err) => setFormError(apiErrorMessage(err, "Unable to create workflow definition.")),
      },
    );
  }

  if (!canManageDefinitions) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Workflow className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to create workflow definitions</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New workflow definition</h1>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}

        <div>
          <label htmlFor="definition-entity-type" className="block text-sm font-medium text-slate-700 mb-1">
            Entity type <span className="text-red-500">*</span>
          </label>
          <input
            id="definition-entity-type"
            required
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            placeholder="e.g. maintenance_ticket"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-500 mt-1">
            A free-text tag matching what a caller passes to POST /workflow/instances/evaluate — no other module wires this in yet.
          </p>
        </div>

        <div>
          <label htmlFor="definition-name" className="block text-sm font-medium text-slate-700 mb-1">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="definition-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          Active
        </label>

        <ConditionEditor value={condition} onChange={setCondition} />

        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium text-slate-700">
              Approval steps <span className="text-red-500">*</span>
            </h2>
            <button type="button" onClick={addRow} className="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline">
              <Plus className="w-3.5 h-3.5" />
              Add step
            </button>
          </div>
          <p className="text-xs text-slate-500 mb-2">Steps sharing the same sequence number run in parallel; groups resolve in ascending order.</p>
          <div className="space-y-3">
            {rows.map((row) => (
              <div key={row.key} className="border border-slate-200 rounded-md p-3 space-y-2">
                <div className="flex flex-wrap gap-2 items-center justify-between">
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-slate-500">Sequence</label>
                    <input
                      type="number"
                      value={row.sequence_order}
                      onChange={(e) => updateRowSequence(row.key, e.target.value)}
                      className="w-20 rounded-md border border-slate-300 px-2 py-1 text-xs"
                    />
                  </div>
                  {rows.length > 1 && (
                    <button type="button" aria-label="Remove step" onClick={() => removeRow(row.key)} className="p-1 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <ApproverPicker value={row} onChange={(next) => updateRow(row.key, next)} />
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={createDefinition.isPending || !entityType.trim() || !name.trim()}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createDefinition.isPending ? "Creating…" : "Create definition"}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-slate-500 px-2">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
