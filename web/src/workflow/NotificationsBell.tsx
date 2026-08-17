import { useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { useMarkNotificationRead, useNotifications } from "./hooks";
import type { Notification } from "./types";

const DROPDOWN_SIZE = 5;

/** Lives outside the /workflow/* permission-tiered surface entirely — auth-only, no permission
 * gate, visible to every signed-in user regardless of role (GET /workflow/notifications has no
 * require_permission dependency, every user manages their own inbox). No polling — this app has
 * no refetchInterval/realtime pattern anywhere yet, and this increment doesn't introduce the
 * first one; TanStack Query's default refetch-on-focus is the only freshness mechanism, same as
 * every other query in this app. Mounted in AppShell's header button cluster. */
export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const notificationsQuery = useNotifications({});
  const markRead = useMarkNotificationRead();

  const notifications = notificationsQuery.data ?? [];
  const unreadCount = notifications.filter((n) => !n.read_at).length;
  const preview = notifications.slice(0, DROPDOWN_SIZE);

  function handleItemClick(n: Notification) {
    if (!n.read_at) markRead.mutate(n.id);
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        onClick={() => setOpen((o) => !o)}
        className="relative inline-flex items-center p-2 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-red-600 text-white text-[10px] font-medium px-1">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-80 max-w-[90vw] rounded-md border border-slate-200 bg-white shadow-lg z-40">
          <div className="px-3 py-2 border-b border-slate-100 text-xs font-medium text-slate-500">Notifications</div>
          <ul className="max-h-80 overflow-y-auto divide-y divide-slate-100">
            {preview.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => handleItemClick(n)}
                  className={`w-full text-left px-3 py-2 hover:bg-slate-50 ${n.read_at ? "" : "bg-[var(--accent-soft)]"}`}
                >
                  <p className="text-sm text-slate-900">{n.title}</p>
                  {n.body && <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.body}</p>}
                  <p className="text-[11px] text-slate-400 mt-0.5">{new Date(n.created_at).toLocaleString()}</p>
                </button>
              </li>
            ))}
            {preview.length === 0 && <li className="px-3 py-4 text-sm text-slate-400 text-center">No notifications yet.</li>}
          </ul>
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="block text-center text-sm text-[var(--accent)] hover:underline px-3 py-2 border-t border-slate-100"
          >
            View all
          </Link>
        </div>
      )}
    </div>
  );
}
