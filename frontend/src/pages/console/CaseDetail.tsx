import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Sparkles, Download } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { CaseDetail as CaseDetailType, HitResponse, LlmDraftResponse } from "@/lib/types";
import { TierBadge } from "@/components/console/TierBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const DECISIONS = ["clear", "approve", "reject"] as const;
const REASON_CODES = ["confirmed_match", "false_positive", "insufficient_evidence", "other"];

function scoreProgram(hit: HitResponse): string[] {
  const programs = hit.scores?.programs;
  return Array.isArray(programs) ? programs.map(String) : [];
}

export default function CaseDetailPage() {
  const { id } = useParams();
  const { session } = useAuth();
  const [caseData, setCaseData] = useState<CaseDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [summary, setSummary] = useState<LlmDraftResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("clear");
  const [rationale, setRationale] = useState("");
  const [draftingRationale, setDraftingRationale] = useState(false);
  const [submittingDecision, setSubmittingDecision] = useState(false);

  const [rfiMessage, setRfiMessage] = useState("");
  const [noteBody, setNoteBody] = useState("");

  const load = useCallback(() => {
    if (!id) return;
    setCaseData(null);
    setError(null);
    api
      .get<CaseDetailType>(`/api/v1/cases/${id}`)
      .then(setCaseData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load case"));
  }, [id]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!id || !caseData) return;
    setSummaryLoading(true);
    api
      .get<LlmDraftResponse>(`/api/v1/cases/${id}/summary`)
      .then(setSummary)
      .catch(() => {
        /* summary is a lazy convenience; a failure here shouldn't block the case */
      })
      .finally(() => setSummaryLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, caseData?.id]);

  function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setActionError(null);
    setActionMessage(null);
    return action()
      .then((result) => {
        setActionMessage(successMessage);
        load();
        return result;
      })
      .catch((err) => {
        setActionError(err instanceof ApiError ? err.message : "Action failed");
        throw err;
      });
  }

  function assignToMe() {
    if (!id || !session) return;
    runAction(
      () => api.post(`/api/v1/cases/${id}/assign`, { assignee_id: session.userId }),
      "Assigned to you.",
    );
  }

  function setDisposition(hitId: number, disposition: "true_match" | "false_positive") {
    if (!id) return;
    runAction(
      () =>
        api.post(`/api/v1/cases/${id}/hits/${hitId}/disposition`, {
          disposition,
          reason_code: REASON_CODES[0],
        }),
      "Hit disposition updated.",
    );
  }

  function submitDecision() {
    if (!id) return;
    setSubmittingDecision(true);
    runAction(
      () => api.post(`/api/v1/cases/${id}/decision`, { decision, is_second_approval: false }),
      `Decision "${decision}" recorded.`,
    ).finally(() => setSubmittingDecision(false));
  }

  function draftRationale() {
    if (!id) return;
    setDraftingRationale(true);
    api
      .post<LlmDraftResponse>(`/api/v1/cases/${id}/decision-rationale-draft`, {
        proposed_decision: decision,
      })
      .then((draft) => setRationale(draft.summary))
      .catch((err) => setActionError(err instanceof ApiError ? err.message : "Draft failed"))
      .finally(() => setDraftingRationale(false));
  }

  function submitRfi() {
    if (!id || !rfiMessage.trim()) return;
    runAction(() => api.post(`/api/v1/cases/${id}/rfi`, { message: rfiMessage }), "RFI sent.").then(
      () => setRfiMessage(""),
    );
  }

  function submitNote() {
    if (!id || !noteBody.trim()) return;
    runAction(() => api.post(`/api/v1/cases/${id}/notes`, { body: noteBody }), "Note added.").then(
      () => setNoteBody(""),
    );
  }

  async function exportPdf() {
    if (!id || !session) return;
    setActionError(null);
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/v1/cases/${id}/export`,
        { headers: { Authorization: `Bearer ${session.accessToken}` } },
      );
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      window.open(URL.createObjectURL(blob), "_blank");
    } catch {
      setActionError("PDF export unavailable in this environment.");
    }
  }

  if (error) {
    return (
      <div className="p-10">
        <div className="flex items-center gap-2 rounded-lg border border-risk-red/30 bg-risk-red/10 p-3 text-sm text-risk-red">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      </div>
    );
  }

  if (!caseData) return <div className="p-10 text-sm text-neutral-900/70">Loading...</div>;

  return (
    <div className="p-6 md:p-10">
      <Link
        to="/app/cases"
        className="inline-flex items-center gap-1 text-sm text-neutral-900/70 hover:text-navy dark:text-white/70"
      >
        <ArrowLeft className="h-4 w-4" /> Back to queue
      </Link>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-navy dark:text-white">Case #{caseData.id}</h1>
          <TierBadge tier={caseData.tier} />
          <span className="text-sm text-neutral-900/70 dark:text-white/70">{caseData.state}</span>
          {caseData.sla_breached && (
            <span className="rounded-full bg-risk-red/10 px-2.5 py-0.5 text-xs font-medium text-risk-red">
              SLA breached
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={assignToMe}>
            Assign to me
          </Button>
          <Button variant="outline" size="sm" onClick={exportPdf}>
            <Download className="h-4 w-4" /> Export PDF
          </Button>
        </div>
      </div>

      {actionError && (
        <div className="mt-4 rounded-lg border border-risk-red/30 bg-risk-red/10 p-3 text-sm text-risk-red">
          {actionError}
        </div>
      )}
      {actionMessage && (
        <div className="mt-4 rounded-lg border border-success-green/30 bg-success-green/10 p-3 text-sm text-success-green">
          {actionMessage}
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardContent className="p-6">
              <h2 className="font-semibold text-navy dark:text-white">Screening hits</h2>
              {caseData.hits.length === 0 && (
                <p className="mt-2 text-sm text-neutral-900/70 dark:text-white/70">
                  No hits recorded for this case.
                </p>
              )}
              <div className="mt-4 space-y-4">
                {caseData.hits.map((hit) => (
                  <div
                    key={hit.id}
                    className="rounded-lg border border-black/5 p-4 dark:border-white/10"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-medium text-navy dark:text-white">{hit.matched_name}</p>
                        <p className="text-xs text-neutral-900/70 dark:text-white/70">
                          Entity #{hit.entity_uid} &middot; {scoreProgram(hit).join(", ") || "no programs listed"}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold text-navy dark:text-white">
                          {Math.round(hit.composite_score)}
                        </div>
                        <div className="text-xs uppercase text-neutral-900/70 dark:text-white/70">
                          {hit.disposition}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDisposition(hit.id, "false_positive")}
                      >
                        Mark false positive
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDisposition(hit.id, "true_match")}
                      >
                        Confirm match
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <h2 className="font-semibold text-navy dark:text-white">Decision</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {DECISIONS.map((d) => (
                  <button
                    key={d}
                    onClick={() => setDecision(d)}
                    className={`rounded-full border px-4 py-1.5 text-sm font-medium capitalize ${
                      decision === d
                        ? "border-teal bg-teal/10 text-teal"
                        : "border-black/10 text-neutral-900/70 dark:border-white/20 dark:text-white/70"
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={4}
                placeholder="Decision rationale"
                className="mt-3 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
              />
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" onClick={draftRationale} disabled={draftingRationale}>
                  <Sparkles className="h-4 w-4" />
                  {draftingRationale ? "Drafting..." : "Draft rationale"}
                </Button>
                <Button size="sm" onClick={submitDecision} disabled={submittingDecision}>
                  {submittingDecision ? "Submitting..." : "Submit decision"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="grid gap-6 p-6 sm:grid-cols-2">
              <div>
                <h2 className="font-semibold text-navy dark:text-white">Request information</h2>
                <textarea
                  value={rfiMessage}
                  onChange={(e) => setRfiMessage(e.target.value)}
                  rows={3}
                  placeholder="What's needed from the applicant?"
                  className="mt-3 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                />
                <Button size="sm" className="mt-2" onClick={submitRfi}>
                  Send RFI
                </Button>
              </div>
              <div>
                <h2 className="font-semibold text-navy dark:text-white">Add note</h2>
                <textarea
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  rows={3}
                  placeholder="Internal note"
                  className="mt-3 w-full rounded-lg border border-black/10 px-3 py-2 text-sm outline-none focus:border-teal focus:ring-1 focus:ring-teal dark:border-white/20 dark:bg-transparent"
                />
                <Button size="sm" className="mt-2" onClick={submitNote}>
                  Add note
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div>
          <Card>
            <CardContent className="p-6">
              <h2 className="flex items-center gap-2 font-semibold text-navy dark:text-white">
                <Sparkles className="h-4 w-4 text-teal" /> Case summary
              </h2>
              {summaryLoading && (
                <p className="mt-2 text-sm text-neutral-900/70 dark:text-white/70">Generating...</p>
              )}
              {summary && (
                <div className="mt-3 space-y-3 text-sm">
                  <p className="text-neutral-900/80 dark:text-white/80">{summary.summary}</p>
                  {summary.key_factors.length > 0 && (
                    <ul className="list-inside list-disc text-neutral-900/70 dark:text-white/70">
                      {summary.key_factors.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  )}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-900/70 dark:text-white/70">
                    <span className="rounded-full bg-teal/10 px-2 py-0.5 text-teal">
                      {summary.suggested_action}
                    </span>
                    <span>confidence: {summary.confidence}</span>
                  </div>
                  {summary.source && <p className="text-xs italic text-neutral-900/70">{summary.source}</p>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
