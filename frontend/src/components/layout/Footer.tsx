import { Link } from "react-router-dom";
import { Logo } from "./Logo";

const COLUMNS: { title: string; links: { label: string; to: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Solutions", to: "/solutions" },
      { label: "Trust Center", to: "/trust" },
      { label: "Sign in", to: "/login" },
    ],
  },
  {
    title: "Company",
    links: [{ label: "Contact", to: "/contact" }],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", to: "/legal/privacy" },
      { label: "Terms of Service", to: "/legal/terms" },
      { label: "Cookie Policy", to: "/legal/cookies" },
      { label: "Responsible Disclosure", to: "/trust#disclosure" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-black/5 bg-neutral-50 dark:border-white/10 dark:bg-navy">
      <div className="container grid gap-10 py-14 md:grid-cols-[1.4fr_repeat(3,1fr)]">
        <div>
          <Logo className="text-navy dark:text-white" />
          <p className="mt-4 max-w-xs text-sm text-neutral-900/60 dark:text-white/60">
            Designed to support BSA/AML, OFAC and FinCEN CIP requirements.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <h3 className="text-sm font-semibold text-navy dark:text-white">{col.title}</h3>
            <ul className="mt-4 space-y-2">
              {col.links.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.to}
                    className="text-sm text-neutral-900/60 hover:text-teal dark:text-white/60"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-black/5 py-6 dark:border-white/10">
        <div className="container flex flex-col gap-2 text-xs text-neutral-900/50 md:flex-row md:items-center md:justify-between dark:text-white/50">
          <p>&copy; {new Date().getFullYear()} SentinelKYC. All rights reserved.</p>
          <p>
            Demo environment: all entities, testimonials and screenshots are illustrative unless
            otherwise noted. Sanctions data is sourced from the public U.S. Treasury OFAC SDN list.
          </p>
        </div>
      </div>
    </footer>
  );
}
