import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { CaseSummary } from "@/lib/types";
import { TierBadge } from "@/components/console/TierBadge";

const TIER_TABS = [
  { value: "", label: "All" },
  { value: "high_risk", label: "High Risk" },
  { value: "review", label: "Review" },
  { value: "clear", label: "Clear" },
  { value: "reject", label: "Reject" },
];

const PAGE_SIZE = 20;

export default function ReviewQueue() {
  const navigate = useNavigate();
  const [tier, setTier] = useState("");
  const [offset, setOffset] = useState(0);
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCases(null);
    setError(null);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (tier) params.set("tier", tier);
    api
      .get<CaseSummary[]>(`/api/v1/cases?${params.toString()}`)
      .then(setCases)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load cases"));
  }, [tier, offset]);

  return (
    <div className="p-6 md:p-10">
      <h1 className="text-2xl font-semibold text-navy dark:text-white">Review Queue</h1>
      <p className="mt-1 text-sm text-neutral-900/70 dark:text-white/70">
        Cases awaiting or recently given a disposition, tenant-scoped by your session.
      </p>

      <div className="mt-6 flex flex-wrap gap-1 border-b border-black/5 dark:border-white/10">
        {TIER_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => {
              setTier(t.value);
              setOffset(0);
            }}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium ${
              tier === t.value
                ? "border-b-2 border-teal text-teal"
                : "text-neutral-900/70 hover:text-navy dark:text-white/70 dark:hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-6 flex items-center gap-2 rounded-lg border border-risk-red/30 bg-risk-red/10 p-3 text-sm text-risk-red">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {!error && cases === null && (
        <div className="mt-6 text-sm text-neutral-900/70 dark:text-white/70">Loading...</div>
      )}

      {cases && cases.length === 0 && (
        <div className="mt-6 text-sm text-neutral-900/70 dark:text-white/70">
          No cases in this view.
        </div>
      )}

      {cases && cases.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-card border border-black/5 dark:border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-900/70 dark:bg-white/5 dark:text-white/70">
              <tr>
                <th className="px-4 py-3">Case</th>
                <th className="px-4 py-3">Tier</th>
                <th className="px-4 py-3">State</th>
                <th className="px-4 py-3">Assignee</th>
                <th className="px-4 py-3">SLA</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/5 dark:divide-white/10">
              {cases.map((c) => (
                <tr
                  key={c.id}
                  className="cursor-pointer hover:bg-navy/5 dark:hover:bg-white/5"
                  onClick={() => navigate(`/app/cases/${c.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-teal">#{c.id}</td>
                  <td className="px-4 py-3">
                    <TierBadge tier={c.tier} />
                  </td>
                  <td className="px-4 py-3">{c.state}</td>
                  <td className="px-4 py-3">{c.assignee_id ?? "Unassigned"}</td>
                  <td className="px-4 py-3">
                    {c.sla_breached ? (
                      <span className="font-medium text-risk-red">Breached</span>
                    ) : c.sla_due_at ? (
                      new Date(c.sla_due_at).toLocaleString()
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="px-4 py-3 text-neutral-900/70 dark:text-white/70">
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex items-center gap-3 text-sm">
        <button
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
          className="rounded-full border border-black/10 px-4 py-1.5 disabled:opacity-40 dark:border-white/20"
        >
          Previous
        </button>
        <button
          disabled={!cases || cases.length < PAGE_SIZE}
          onClick={() => setOffset((o) => o + PAGE_SIZE)}
          className="rounded-full border border-black/10 px-4 py-1.5 disabled:opacity-40 dark:border-white/20"
        >
          Next
        </button>
      </div>
    </div>
  );
}
