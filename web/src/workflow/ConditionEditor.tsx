import type { ConditionOperator } from "./types";
import { CONDITION_OPERATORS } from "./types";

export interface ConditionFields {
  condition_attribute: string | null;
  condition_operator: ConditionOperator | null;
  condition_value: string | number | boolean | null;
}

type ValueType = "string" | "number" | "boolean";

function inferValueType(value: string | number | boolean | null): ValueType {
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "string";
}

/** The attribute/operator/value trio behind WorkflowDefinition.condition_* — all three are a
 * single logical unit server-side (WorkflowService._validate_condition_triple: all-three-or-none
 * — a bare "compare to null" isn't supported), so the "only open when a condition matches"
 * checkbox clears (or seeds) all three together rather than letting them go out of sync. Shared
 * by DefinitionFormPage (creation) and DefinitionDetailPage's inline Overview edit (PATCH).
 *
 * condition_value is compared with raw Python ==/>/etc. (WorkflowService._condition_matches) —
 * the string "3" and the number 3 are NOT equal under gt/lt, and a TypeError from comparing
 * mismatched types is treated as "no match," not an error — so the value type genuinely changes
 * matching behavior, not just display. The type selector lets the caller pick which JSON type
 * condition_value serializes as. */
export function ConditionEditor({ value, onChange }: { value: ConditionFields; onChange: (next: ConditionFields) => void }) {
  const hasCondition = value.condition_attribute !== null;
  const valueType = inferValueType(value.condition_value);

  function enableCondition(enabled: boolean) {
    onChange(
      enabled
        ? { condition_attribute: "", condition_operator: "eq", condition_value: "" }
        : { condition_attribute: null, condition_operator: null, condition_value: null },
    );
  }

  function setValueType(type: ValueType) {
    onChange({ ...value, condition_value: type === "boolean" ? false : type === "number" ? 0 : "" });
  }

  return (
    <div className="space-y-2">
      <label className="flex items-center gap-1.5 text-sm text-slate-600">
        <input type="checkbox" checked={hasCondition} onChange={(e) => enableCondition(e.target.checked)} />
        Only open when a condition matches
      </label>

      {hasCondition && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pl-1">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Attribute</label>
            <input
              value={value.condition_attribute ?? ""}
              onChange={(e) => onChange({ ...value, condition_attribute: e.target.value })}
              placeholder="e.g. amount"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Operator</label>
            <select
              value={value.condition_operator ?? "eq"}
              onChange={(e) => onChange({ ...value, condition_operator: e.target.value as ConditionOperator })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
            >
              {CONDITION_OPERATORS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Value type</label>
            <select
              value={valueType}
              onChange={(e) => setValueType(e.target.value as ValueType)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
            >
              <option value="string">Text</option>
              <option value="number">Number</option>
              <option value="boolean">True/false</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Value</label>
            {valueType === "boolean" ? (
              <select
                value={String(value.condition_value ?? false)}
                onChange={(e) => onChange({ ...value, condition_value: e.target.value === "true" })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
              >
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : (
              <input
                type={valueType === "number" ? "number" : "text"}
                value={value.condition_value === null ? "" : String(value.condition_value)}
                onChange={(e) => onChange({ ...value, condition_value: valueType === "number" ? Number(e.target.value) : e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
