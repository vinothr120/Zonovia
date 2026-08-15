import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

/**
 * Deliberately slim: one header (app name, signed-in user's email, sign-out button), no
 * sidebar/nav. There's exactly one protected route right now (ScanPage). Add real navigation
 * when a second page exists.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-svh bg-slate-50 flex flex-col">
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between gap-2 px-4 sticky top-0 z-30">
        <span className="font-semibold text-slate-900 truncate">Zonovia</span>
        <div className="flex items-center gap-3 shrink-0">
          <span className="hidden sm:inline text-sm text-slate-500 truncate max-w-[16rem]">{me?.email}</span>
          <button
            type="button"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => void handleLogout()}
            className="inline-flex items-center gap-1.5 text-sm px-2.5 py-1.5 rounded-md text-slate-600 hover:text-red-600 hover:bg-red-50 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>
      <main className="flex-1 max-w-3xl mx-auto px-4 py-8 w-full">{children}</main>
    </div>
  );
}
