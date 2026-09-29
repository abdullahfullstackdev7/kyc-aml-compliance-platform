import { Link } from "react-router-dom";
import { ShieldCheck, Gauge, FileCheck2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal } from "@/components/Reveal";
import { GradientVisual } from "@/components/GradientVisual";

const TRUST_BAR = [
  "Meridian Trust Bank",
  "Vantage Capital Partners",
  "Northlake Financial",
  "Pier Street Payments",
  "Arcadia Digital Assets",
  "Continental Fintech Group",
];

const STATS = [
  { label: "SDN entries screened against", value: "~18,700" },
  { label: "Sanctions list last updated", value: "Every 6 hours" },
  { label: "Median decision time", value: "< 3 min" },
];

const PILLARS = [
  {
    icon: ShieldCheck,
    title: "Screen",
    body: "Every applicant is matched against the U.S. Treasury OFAC SDN list using hybrid fuzzy, phonetic and multilingual vector search.",
  },
  {
    icon: Gauge,
    title: "Decide",
    body: "Risk-tiered routing auto-approves clean applicants and sends the rest to a reviewer with a scored, explainable case.",
  },
  {
    icon: FileCheck2,
    title: "Prove",
    body: "Every transition is written to an immutable, hash-chained audit log, ready for an examiner at any time.",
  },
];

const WORKFLOW_STEPS = ["Intake", "Verify", "Screen", "Decide", "Audit"];

const TESTIMONIALS = [
  {
    quote:
      "The review queue cut our average handling time roughly in half within the first month.",
    name: "Compliance Lead, illustrative persona",
  },
  {
    quote: "Having the full audit chain a click away made our last exam noticeably shorter.",
    name: "MLRO, illustrative persona",
  },
];

export default function Home() {
  return (
    <>
      <section className="border-b border-black/5 bg-neutral-50 dark:border-white/10 dark:bg-navy">
        <div className="container grid items-center gap-10 py-16 md:grid-cols-2 md:py-24">
          <Reveal>
            <h1 className="text-balance font-serif text-4xl font-semibold leading-tight text-navy dark:text-white md:text-5xl">
              Onboard customers with confidence. Screen every party against the sanctions list
              that matters.
            </h1>
            <p className="mt-5 max-w-lg text-lg text-neutral-900/70 dark:text-white/70">
              SentinelKYC runs identity intake, document verification, sanctions screening and
              risk-tiered decisioning in one auditable workflow, built entirely on open data and
              open-source matching.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link to="/login">
                  Get started <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/solutions">Explore solutions</Link>
              </Button>
            </div>
          </Reveal>
          <Reveal delay={0.1}>
            <GradientVisual label="Operations center overview" className="aspect-[4/3] w-full" />
          </Reveal>
        </div>
      </section>

      <section className="border-b border-black/5 py-8 dark:border-white/10">
        <div className="container">
          <p className="text-center text-xs font-medium uppercase tracking-wide text-neutral-900/50 dark:text-white/50">
            Trusted by compliance teams at
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-10 gap-y-3 text-sm font-semibold text-neutral-900/40 dark:text-white/40">
            {TRUST_BAR.map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-black/5 bg-navy py-12 text-white dark:border-white/10">
        <div className="container grid gap-8 sm:grid-cols-3">
          {STATS.map((stat) => (
            <div key={stat.label} className="text-center sm:text-left">
              <div className="text-3xl font-semibold">{stat.value}</div>
              <div className="mt-1 text-sm text-white/60">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="py-16 md:py-24">
        <div className="container">
          <Reveal>
            <h2 className="text-center font-serif text-3xl font-semibold text-navy dark:text-white">
              One workflow, three jobs
            </h2>
          </Reveal>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {PILLARS.map((pillar, i) => (
              <Reveal key={pillar.title} delay={i * 0.08}>
                <Card>
                  <CardHeader>
                    <pillar.icon className="h-8 w-8 text-teal" />
                    <CardTitle className="mt-3">{pillar.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-neutral-900/70 dark:text-white/70">
                    {pillar.body}
                  </CardContent>
                </Card>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-black/5 bg-neutral-50 py-16 dark:border-white/10 dark:bg-navy/60">
        <div className="container">
          <Reveal>
            <h2 className="text-center font-serif text-3xl font-semibold text-navy dark:text-white">
              From application to audit-ready case
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-2">
              {WORKFLOW_STEPS.map((step, i) => (
                <div key={step} className="flex items-center gap-2">
                  <div className="rounded-full border border-teal/40 bg-white px-5 py-2 text-sm font-medium text-navy dark:bg-navy dark:text-white">
                    {step}
                  </div>
                  {i < WORKFLOW_STEPS.length - 1 && (
                    <ArrowRight className="h-4 w-4 text-teal" aria-hidden="true" />
                  )}
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      <section className="py-16 md:py-24">
        <div className="container">
          <Reveal>
            <h2 className="text-center font-serif text-3xl font-semibold text-navy dark:text-white">
              Built on real controls, not just claims
            </h2>
          </Reveal>
          <div className="mt-10 grid gap-6 md:grid-cols-2">
            <Reveal>
              <Card>
                <CardContent className="p-8">
                  <h3 className="font-semibold text-navy dark:text-white">Security and trust</h3>
                  <ul className="mt-4 space-y-2 text-sm text-neutral-900/70 dark:text-white/70">
                    <li>AES-256-GCM field-level encryption with per-tenant key versions</li>
                    <li>Row-Level Security enforced at the database, not just the API</li>
                    <li>Append-only, hash-chained audit log, verifiable per tenant</li>
                    <li>Mandatory MFA and RBAC/ABAC for every reviewer role</li>
                  </ul>
                  <Link
                    to="/trust"
                    className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-teal"
                  >
                    Visit the Trust Center <ArrowRight className="h-4 w-4" />
                  </Link>
                </CardContent>
              </Card>
            </Reveal>
            <Reveal delay={0.08}>
              <GradientVisual label="Case review console preview" variant="teal" className="h-full" />
            </Reveal>
          </div>
        </div>
      </section>

      <section className="border-t border-black/5 bg-neutral-50 py-16 dark:border-white/10 dark:bg-navy/60">
        <div className="container grid gap-6 md:grid-cols-2">
          {TESTIMONIALS.map((t, i) => (
            <Reveal key={t.name} delay={i * 0.08}>
              <Card>
                <CardContent className="p-8">
                  <p className="text-lg text-navy dark:text-white">&ldquo;{t.quote}&rdquo;</p>
                  <p className="mt-4 text-sm text-neutral-900/50 dark:text-white/50">
                    {t.name} &mdash; illustrative, not an actual customer
                  </p>
                </CardContent>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="py-16 text-center md:py-24">
        <div className="container">
          <Reveal>
            <h2 className="font-serif text-3xl font-semibold text-navy dark:text-white">
              Ready to see it on your own data?
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-neutral-900/70 dark:text-white/70">
              Sign in to the console with the demo tenant, or start an applicant journey through
              the onboarding portal.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Button size="lg" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/contact">Contact sales</Link>
              </Button>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
