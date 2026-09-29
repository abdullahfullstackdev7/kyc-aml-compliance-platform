import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Logo } from "./Logo";
import { Button } from "@/components/ui/button";

const NAV_LINKS = [
  { to: "/solutions", label: "Solutions" },
  { to: "/trust", label: "Trust Center" },
];

export function Header() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-black/5 bg-white/85 backdrop-blur dark:border-white/10 dark:bg-navy/85">
      <div className="container flex h-16 items-center justify-between">
        <Logo className="text-navy dark:text-white" />

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "text-teal"
                    : "text-navy/80 hover:text-navy dark:text-white/80 dark:hover:text-white"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/contact">Contact sales</Link>
          </Button>
          <Button size="sm" asChild>
            <Link to="/login">Sign in</Link>
          </Button>
        </div>

        <button
          className="md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {open && (
        <div className="border-t border-black/5 px-4 pb-4 md:hidden dark:border-white/10">
          <nav className="flex flex-col gap-1 pt-2" aria-label="Primary mobile">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="rounded-lg px-3 py-2 text-sm font-medium hover:bg-navy/5 dark:hover:bg-white/10"
                onClick={() => setOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <Link
              to="/login"
              className="mt-2 rounded-full bg-navy px-4 py-2 text-center text-sm font-medium text-white"
              onClick={() => setOpen(false)}
            >
              Sign in
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
