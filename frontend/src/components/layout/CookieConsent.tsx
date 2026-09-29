import { useEffect, useState } from "react";

const STORAGE_KEY = "sentinelkyc-cookie-consent";

export function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  function choose(value: "accepted" | "rejected") {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      /* private browsing or blocked storage: consent just won't persist */
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-black/10 bg-white p-4 shadow-subtle dark:border-white/10 dark:bg-navy">
      <div className="container flex flex-col items-start gap-3 md:flex-row md:items-center md:justify-between">
        <p className="text-sm text-neutral-900/70 dark:text-white/70">
          We use cookies to run this demo site and understand aggregate usage. See our{" "}
          <a href="/legal/cookies" className="underline">
            Cookie Policy
          </a>
          .
        </p>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={() => choose("rejected")}
            className="rounded-full border border-black/10 px-4 py-2 text-sm font-medium dark:border-white/20"
          >
            Reject
          </button>
          <button
            onClick={() => choose("accepted")}
            className="rounded-full bg-navy px-4 py-2 text-sm font-medium text-white"
          >
            Accept
          </button>
        </div>
      </div>
    </div>
  );
}
