import type { ReactNode } from "react";
import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Boxes, ChevronDown, ClipboardList, LogOut, MapPin, ScanLine, Tag } from "lucide-react";
import { useAuth } from "../auth/AuthContext";

const navLinkBase = "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap";
const navLinkInactive = "text-slate-600 hover:bg-slate-100 hover:text-slate-900";
const navLinkActive = "bg-[var(--accent-soft)] text-[var(--accent)]";

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `${navLinkBase} ${isActive ? navLinkActive : navLinkInactive}`;
}

/**
 * Header (app name, signed-in user's email, sign-out button) unchanged from the nav-less
 * version, now with a left sidebar that collapses to a horizontal, scrollable tab strip below
 * the `sm` breakpoint. `main` no longer imposes a global max-width — pages own their own
 * container width now that a wide asset table exists alongside the narrow scan screen.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [catalogOpen, setCatalogOpen] = useState(location.pathname.startsWith("/catalog"));

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

      <div className="flex-1 flex flex-col sm:flex-row min-w-0">
        <nav className="shrink-0 bg-white border-b sm:border-b-0 sm:border-r border-slate-200 sm:w-56 sm:sticky sm:top-14 sm:self-start sm:h-[calc(100svh-3.5rem)] overflow-x-auto sm:overflow-y-auto px-2 py-2 sm:py-3">
          <div className="flex sm:flex-col gap-1">
            <NavLink to="/assets" className={navLinkClass}>
              <Boxes className="w-4 h-4 shrink-0" />
              Assets
            </NavLink>

            <div className="sm:contents">
              <button
                type="button"
                onClick={() => setCatalogOpen((open) => !open)}
                aria-expanded={catalogOpen}
                className={`${navLinkBase} ${navLinkInactive} sm:w-full sm:justify-between`}
              >
                <span className="flex items-center gap-2">
                  <Tag className="w-4 h-4 shrink-0" />
                  Asset Catalog
                </span>
                <ChevronDown className={`w-4 h-4 transition-transform shrink-0 ${catalogOpen ? "rotate-180" : ""}`} />
              </button>
              {catalogOpen && (
                <div className="flex sm:flex-col gap-1 sm:pl-6">
                  <NavLink to="/catalog/categories" className={navLinkClass}>
                    Categories
                  </NavLink>
                  <NavLink to="/catalog/types" className={navLinkClass}>
                    Types
                  </NavLink>
                  <NavLink to="/catalog/vendors" className={navLinkClass}>
                    Vendors
                  </NavLink>
                </div>
              )}
            </div>

            <NavLink to="/locations" className={navLinkClass}>
              <MapPin className="w-4 h-4 shrink-0" />
              Locations
            </NavLink>
            <NavLink to="/inventory" className={navLinkClass}>
              <ClipboardList className="w-4 h-4 shrink-0" />
              Inventory
            </NavLink>
            <NavLink to="/scan" className={navLinkClass}>
              <ScanLine className="w-4 h-4 shrink-0" />
              Scan
            </NavLink>
          </div>
        </nav>

        <main className="flex-1 min-w-0 px-4 py-8">{children}</main>
      </div>
    </div>
  );
}
