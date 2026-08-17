import { useUsersLookup } from "../users/hooks";
import { useRoles } from "./hooks";

export interface ApproverFields {
  approver_user_id: string | null;
  approver_role_key: string | null;
}

type ApproverMode = "user" | "role";

/** User/Role toggle shared by DefinitionFormPage's local step rows and StepsSection's add/edit
 * rows — one place to get the XOR enforcement right. approver_role_key is the Role.name string
 * (WorkflowService resolves it via RoleRepository.get_by_name), not a role id, so the role
 * <select>'s option value is r.name. Switching mode clears the other field so the two can never
 * both be set (or both stay null) when the caller submits, mirroring the exactly-one-of rule
 * WorkflowService.add_step/create_definition/update_step all enforce server-side. */
export function ApproverPicker({ value, onChange }: { value: ApproverFields; onChange: (next: ApproverFields) => void }) {
  const usersLookup = useUsersLookup();
  const rolesQuery = useRoles();
  const mode: ApproverMode = value.approver_role_key !== null ? "role" : "user";

  function setMode(next: ApproverMode) {
    onChange(next === "user" ? { approver_user_id: "", approver_role_key: null } : { approver_user_id: null, approver_role_key: "" });
  }

  const users = usersLookup.data ?? [];
  const roles = rolesQuery.data ?? [];

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <div className="inline-flex rounded-md border border-slate-300 overflow-hidden shrink-0">
        <button
          type="button"
          onClick={() => setMode("user")}
          className={`text-xs px-2 py-1.5 ${mode === "user" ? "bg-[var(--accent)] text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
        >
          User
        </button>
        <button
          type="button"
          onClick={() => setMode("role")}
          className={`text-xs px-2 py-1.5 border-l border-slate-300 ${mode === "role" ? "bg-[var(--accent)] text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
        >
          Role
        </button>
      </div>

      {mode === "user" ? (
        usersLookup.canViewUsers ? (
          <select
            value={value.approver_user_id ?? ""}
            onChange={(e) => onChange({ approver_user_id: e.target.value, approver_role_key: null })}
            className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
          >
            <option value="">Select a user…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.email}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-slate-500">You don't have permission to view users.</p>
        )
      ) : (
        <select
          value={value.approver_role_key ?? ""}
          onChange={(e) => onChange({ approver_user_id: null, approver_role_key: e.target.value })}
          className="flex-1 min-w-[10rem] rounded-md border border-slate-300 px-2 py-1.5 text-sm bg-white"
        >
          <option value="">Select a role…</option>
          {roles.map((r) => (
            <option key={r.id} value={r.name}>
              {r.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
