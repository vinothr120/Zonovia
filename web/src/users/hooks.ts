import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { api } from "../core/apiClient";

export interface UserSummary {
  id: string;
  email: string;
}

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** Custodian resolution degrades gracefully rather than erroring: this hook only fires the
 * request if the caller has users.view (not guaranteed for every role, e.g. Viewer). A missing
 * entry in `map` — whether from the permission being absent or the custodian's id simply not
 * being in the first page — is meant to be treated as "unknown", not a failure; see
 * custodianLabel below. */
export function useUsersLookup() {
  const { me } = useAuth();
  const canViewUsers = me?.permissions.includes("users.view") ?? false;

  const query = useQuery({
    queryKey: ["users-lookup"],
    queryFn: () => api.get<UserSummary[]>("/users", { page_size: 100 }),
    enabled: canViewUsers,
    staleTime: REFERENCE_STALE_TIME,
  });

  const map = useMemo(() => new Map((query.data ?? []).map((u) => [u.id, u])), [query.data]);
  return { ...query, map, canViewUsers };
}

/** null -> "Unassigned"; found in the lookup map -> the resolved email; otherwise (permission
 * absent, or id outside the first 100 users fetched) -> a neutral badge with a truncated id.
 * Never throws — this is a display fallback, not an error path. */
export function custodianLabel(userId: string | null, map: Map<string, UserSummary>): string {
  if (!userId) return "Unassigned";
  const user = map.get(userId);
  if (user) return user.email;
  return `Assigned (${userId.slice(0, 8)}…)`;
}
