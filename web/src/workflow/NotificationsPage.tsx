import { useState } from "react";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useMarkNotificationRead, useNotifications } from "./hooks";

/** Top-level /notifications, not nested under /workflow — auth-only, no permission gate, same
 * reasoning as NotificationsBell. Server-ordered created_at desc — no client sort needed. */
export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const notificationsQuery = useNotifications({ unread_only: unreadOnly });
  const markRead = useMarkNotificationRead();

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Notifications</h1>
      </div>

      <label className="flex items-center gap-1.5 text-sm text-slate-600">
        <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
        Unread only
      </label>

      {notificationsQuery.isLoading && <LoadingState />}
      {notificationsQuery.isError && (
        <ErrorState message={apiErrorMessage(notificationsQuery.error, "Unable to load notifications.")} onRetry={() => void notificationsQuery.refetch()} />
      )}

      {notificationsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {notificationsQuery.data.map((n) => (
            <div key={n.id} className={`p-4 flex items-start justify-between gap-3 ${n.read_at ? "" : "bg-[var(--accent-soft)]"}`}>
              <div>
                <p className="text-sm text-slate-900 font-medium">{n.title}</p>
                {n.body && <p className="text-sm text-slate-600 mt-0.5">{n.body}</p>}
                <p className="text-xs text-slate-400 mt-1">{new Date(n.created_at).toLocaleString()}</p>
              </div>
              {!n.read_at && (
                <button
                  type="button"
                  disabled={markRead.isPending}
                  onClick={() => markRead.mutate(n.id)}
                  className="shrink-0 text-xs border border-slate-300 text-slate-700 rounded-md px-2 py-1 hover:bg-slate-50 disabled:opacity-60"
                >
                  Mark read
                </button>
              )}
            </div>
          ))}
          {notificationsQuery.data.length === 0 && <EmptyState message="No notifications yet." />}
        </div>
      )}
    </div>
  );
}
