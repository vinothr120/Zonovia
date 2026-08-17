import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Workflow } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage } from "../core/ui/StateViews";
import { useDefinitions, useEvaluateInstance } from "./hooks";

/** Registered at /workflow/instances/evaluate, BEFORE the /workflow/instances/:instanceId route
 * in App.tsx — otherwise "evaluate" would match the :instanceId param and this page would never
 * be reached. A dedicated page, not an inline panel on InstancesListPage, so the banner below
 * has room to be explicit: today, the ONLY way an ApprovalInstance is ever created is this
 * manual trigger. No real module (Maintenance, Flow, Inventory) calls
 * WorkflowService.evaluate_and_maybe_open yet — this form exists for a Tenant Admin to test a
 * definition's condition/routing before (eventually) a real module wires the engine into its
 * write path. Gated workflow.manage_definitions, same as the endpoint itself (router.py:
 * "Deliberately conservative... not the primary integration path"). */
export function EvaluateInstancePage() {
  const { me } = useAuth();
  const canEvaluate = me?.permissions.includes("workflow.manage_definitions") ?? false;
  const navigate = useNavigate();
  const evaluateInstance = useEvaluateInstance();
  const definitionsQuery = useDefinitions({});

  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [contextText, setContextText] = useState("{}");
  const [formError, setFormError] = useState<string | null>(null);
  const [noMatch, setNoMatch] = useState(false);

  // Values already seen across existing definitions, offered as a <datalist> to reduce silent
  // typo mismatches between what a definition's entity_type says and what gets typed here — a
  // typo here means evaluate_and_maybe_open silently finds no matching definition, not an error.
  const knownEntityTypes = useMemo(() => {
    const set = new Set((definitionsQuery.data ?? []).map((d) => d.entity_type));
    return [...set].sort();
  }, [definitionsQuery.data]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setNoMatch(false);
    if (!entityType.trim() || !entityId.trim()) return;

    let context: Record<string, unknown>;
    try {
      const parsed: unknown = contextText.trim() ? JSON.parse(contextText) : {};
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setFormError("Context must be a JSON object, e.g. {\"amount\": 100}.");
        return;
      }
      context = parsed as Record<string, unknown>;
    } catch {
      setFormError("Context is not valid JSON.");
      return;
    }

    evaluateInstance.mutate(
      { entity_type: entityType.trim(), entity_id: entityId.trim(), context },
      {
        onSuccess: (instance) => {
          if (instance === null) {
            setNoMatch(true);
            return;
          }
          navigate(`/workflow/instances/${instance.id}`, { replace: true });
        },
        onError: (err) => setFormError(apiErrorMessage(err, "Unable to evaluate this entity.")),
      },
    );
  }

  if (!canEvaluate) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <Workflow className="w-8 h-8 mx-auto text-slate-300 mb-3" />
        <h2 className="text-slate-900 font-semibold mb-1">You don't have permission to evaluate approval instances</h2>
        <p className="text-sm text-slate-500">Contact a tenant admin if you believe this is a mistake.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Evaluate entity</h1>
      </div>

      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-2.5">
        <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900">
          This is a manual admin/testing trigger, not a real business action. No module in Zonovia today (Maintenance, Flow, Inventory) calls the
          approval engine automatically — this form lets you manually check whether an entity_type/context combination matches a workflow
          definition and opens a real approval instance if it does.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        {formError && <div className="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{formError}</div>}
        {noMatch && (
          <div className="rounded-md bg-slate-50 border border-slate-200 text-slate-700 text-sm px-3 py-2">
            Nothing matched — either no active definition's condition matched this context, or an approval instance is already open for this
            entity.
          </div>
        )}

        <div>
          <label htmlFor="evaluate-entity-type" className="block text-sm font-medium text-slate-700 mb-1">
            Entity type <span className="text-red-500">*</span>
          </label>
          <input
            id="evaluate-entity-type"
            required
            list="known-entity-types"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <datalist id="known-entity-types">
            {knownEntityTypes.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>

        <div>
          <label htmlFor="evaluate-entity-id" className="block text-sm font-medium text-slate-700 mb-1">
            Entity id (UUID) <span className="text-red-500">*</span>
          </label>
          <input
            id="evaluate-entity-id"
            required
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono"
          />
        </div>

        <div>
          <label htmlFor="evaluate-context" className="block text-sm font-medium text-slate-700 mb-1">
            Context (JSON)
          </label>
          <textarea
            id="evaluate-context"
            value={contextText}
            onChange={(e) => setContextText(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono"
          />
          <p className="text-xs text-slate-500 mt-1">Matched against any active definition's condition_attribute for this entity_type.</p>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={evaluateInstance.isPending || !entityType.trim() || !entityId.trim()}
            className="rounded-md bg-[var(--accent)] text-white text-sm font-medium px-4 py-2 hover:bg-[var(--accent-dark)] disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {evaluateInstance.isPending ? "Evaluating…" : "Evaluate"}
          </button>
        </div>
      </form>
    </div>
  );
}
