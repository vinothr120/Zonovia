import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useToast } from "../core/ui/ToastContext";
import type { ConditionFields } from "./ConditionEditor";
import { ConditionEditor } from "./ConditionEditor";
import { DefinitionActiveBadge } from "./DefinitionsListPage";
import { StepsSection } from "./StepsSection";
import { useDefinition, useDeleteDefinition, useUpdateDefinition } from "./hooks";

/** Matches TicketDetailPage's pattern: inline-edit Overview card (toggled, not a separate
 * /edit route) plus an embedded sub-section (StepsSection, this module's AssetScheduleSection
 * analog). PATCH /workflow/definitions/{id} never touches steps — add/update/delete step are
 * separate endpoints StepsSection calls directly — matching the real endpoint split. entity_type
 * is immutable after creation (not a field on WorkflowDefinitionUpdate), so it's display-only
 * here, never part of the edit form. */
export function DefinitionDetailPage() {
  const { definitionId } = useParams<{ definitionId: string }>();
  const { me } = useAuth();
  const canManageDefinitions = me?.permissions.includes("workflow.manage_definitions") ?? false;
  const { showToast } = useToast();
  const navigate = useNavigate();

  const definitionQuery = useDefinition(definitionId);
  const updateDefinition = useUpdateDefinition(definitionId ?? "");
  const deleteDefinition = useDeleteDefinition();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [condition, setCondition] = useState<ConditionFields>({ condition_attribute: null, condition_operator: null, condition_value: null });
  const [editError, setEditError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const definition = definitionQuery.data;

  function startEditing() {
    if (!definition) return;
    setName(definition.name);
    setIsActive(definition.is_active);
    setCondition({
      condition_attribute: definition.condition_attribute,
      condition_operator: definition.condition_operator,
      condition_value: definition.condition_value,
    });
    setEditError(null);
    setEditing(true);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setEditError(null);
    if (!name.trim()) return;
    updateDefinition.mutate(
      {
        name: name.trim(),
        is_active: isActive,
        condition_attribute: condition.condition_attribute,
        condition_operator: condition.condition_operator,
        condition_value: condition.condition_value,
      },
      {
        onSuccess: () => {
          setEditing(false);
          showToast("Definition updated.", "success");
        },
        onError: (err) => setEditError(apiErrorMessage(err, "Unable to update definition.")),
      },
    );
  }

  function handleDelete() {
    if (!definitionId) return;
    setDeleteError(null);
    deleteDefinition.mutate(definitionId, {
      onSuccess: () => {
        showToast("Definition deleted.", "success");
        navigate("/workflow/definitions", { replace: true });
      },
      onError: (err) => setDeleteError(apiErrorMessage(err, "Unable to delete definition.")),
    });
  }

  if (!definitionId) return null;
  if (definitionQuery.isLoading) return <LoadingState />;
  if (definitionQuery.isError) {
    return <ErrorState message={apiErrorMessage(definitionQuery.error, "Unable to load workflow definition.")} onRetry={() => void definitionQuery.refetch()} />;
  }
  if (!definition) return null;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/workflow/definitions" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to workflow definitions
        </Link>
      </div>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{definition.name}</h1>
          <p className="text-sm text-slate-500 font-mono">{definition.entity_type}</p>
        </div>
        {canManageDefinitions && !editing && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={startEditing}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 text-slate-700 text-sm font-medium px-3 py-1.5 hover:bg-slate-50"
            >
              <Pencil className="w-3.5 h-3.5" />
              Edit
            </button>
            <button
              type="button"
              disabled={deleteDefinition.isPending}
              onClick={handleDelete}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-200 text-red-600 text-sm font-medium px-3 py-1.5 hover:bg-red-50 disabled:opacity-60"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {deleteDefinition.isPending ? "Deleting…" : "Delete"}
            </button>
          </div>
        )}
      </div>

      {deleteError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{deleteError}</div>}

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Overview</h2>

        {editing ? (
          <form onSubmit={handleSubmit} className="space-y-3">
            {editError && <div className="text-red-600 text-xs">{editError}</div>}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Name <span className="text-red-500">*</span>
              </label>
              <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
            </div>
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
              Active
            </label>
            <ConditionEditor value={condition} onChange={setCondition} />
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={updateDefinition.isPending || !name.trim()} className="text-sm bg-[var(--accent)] text-white rounded-md px-3 py-1.5 disabled:opacity-60">
                {updateDefinition.isPending ? "Saving…" : "Save changes"}
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
              <DefinitionActiveBadge isActive={definition.is_active} />
            </dd>
            <dt className="text-slate-500">Condition</dt>
            <dd className="text-slate-900 font-mono text-xs">
              {definition.condition_attribute
                ? `${definition.condition_attribute} ${definition.condition_operator} ${JSON.stringify(definition.condition_value)}`
                : "always opens (no condition)"}
            </dd>
            <dt className="text-slate-500">Created</dt>
            <dd className="text-slate-900">{new Date(definition.created_at).toLocaleString()}</dd>
          </dl>
        )}
      </div>

      <StepsSection definitionId={definitionId} canManage={canManageDefinitions} />
    </div>
  );
}
