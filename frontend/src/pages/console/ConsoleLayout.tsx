import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LayoutList, LogOut, BarChart3 } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { useAuth } from "@/lib/auth";

export function ConsoleLayout({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex min-h-screen bg-neutral-50 dark:bg-navy">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-black/5 bg-white p-4 md:flex dark:border-white/10 dark:bg-navy/60">
        <Logo className="px-2 text-navy dark:text-white" />
        <nav className="mt-8 flex flex-col gap-1">
          <Link
            to="/app/cases"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-navy hover:bg-navy/5 dark:text-white dark:hover:bg-white/10"
          >
            <LayoutList className="h-4 w-4" />
            Review Queue
          </Link>
          <Link
            to="/app/analytics"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-navy hover:bg-navy/5 dark:text-white dark:hover:bg-white/10"
          >
            <BarChart3 className="h-4 w-4" />
            Analytics
          </Link>
        </nav>
        <div className="mt-auto space-y-2 border-t border-black/5 pt-4 text-xs text-neutral-900/50 dark:border-white/10 dark:text-white/50">
          {session && (
            <>
              <div>User #{session.userId}</div>
              <div className="truncate">{session.roles.join(", ") || "no roles"}</div>
            </>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-neutral-900/70 hover:text-risk-red dark:text-white/70"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-x-hidden">{children}</main>
    </div>
  );
}
