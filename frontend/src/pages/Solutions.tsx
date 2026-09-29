import { UserCheck, Building2, RefreshCw, ClipboardList } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { Reveal } from "@/components/Reveal";

const SOLUTIONS = [
  {
    icon: UserCheck,
    title: "Customer onboarding",
    problem: "Manual identity checks slow down account opening and are inconsistent across teams.",
    capabilities: [
      "Multi-step applicant portal with document capture and live quality hints",
      "OCR, MRZ parsing and checksum validation on every uploaded ID",
      "Automatic sanctions screening the moment documents verify",
    ],
    outcomes: "Roughly 85 percent of clean applicants are auto-approved with no reviewer touch.",
  },
  {
    icon: Building2,
    title: "Vendor and third-party screening",
    problem: "Third parties are onboarded ad hoc, with screening as an afterthought.",
    capabilities: [
      "Ad-hoc single search and CSV batch upload against the OFAC SDN list",
      "Entity resolution across aliases, transliterations and weak/strong AKAs",
      "Downloadable, timestamped results for procurement records",
    ],
    outcomes: "Every vendor relationship gets the same screening rigor as a retail customer.",
  },
  {
    icon: RefreshCw,
    title: "Continuous monitoring",
    problem: "A customer cleared last year may be newly listed today.",
    capabilities: [
      "Every sanctions list refresh diffs against the prior version",
      "Only customers whose risk profile intersects a change are rescreened",
      "New alerts route into the same risk-tiered case queue as onboarding",
    ],
    outcomes: "No customer goes more than one list cycle without being re-checked.",
  },
  {
    icon: ClipboardList,
    title: "Case management",
    problem: "Spreadsheet-based review queues have no SLA tracking or audit trail.",
    capabilities: [
      "Tiered review queue with SLA countdowns and keyboard-driven triage",
      "Four-eyes dual approval on high-risk decisions",
      "Every disposition, note and decision written to an immutable audit log",
    ],
    outcomes: "Full, exportable case history ready for an examiner at any time.",
  },
];

const FAQ = [
  {
    q: "What sanctions data does SentinelKYC screen against?",
    a: "The public U.S. Treasury OFAC Specially Designated Nationals (SDN) list, ingested and refreshed automatically on a schedule.",
  },
  {
    q: "Can a reviewer override an automated tier?",
    a: "Yes. Every automated routing decision lands in a queue a human reviewer can clear, escalate or reject, and every action is audited.",
  },
  {
    q: "Is customer data encrypted?",
    a: "Personally identifiable fields are encrypted at rest with per-tenant keys, and access is scoped by row-level security in the database.",
  },
];

export default function Solutions() {
  return (
    <div className="container py-16 md:py-24">
      <Reveal>
        <h1 className="font-serif text-4xl font-semibold text-navy dark:text-white">Solutions</h1>
        <p className="mt-3 max-w-2xl text-lg text-neutral-900/70 dark:text-white/70">
          One workflow covers onboarding, vendor screening, ongoing monitoring and case
          management, so nothing depends on a spreadsheet.
        </p>
      </Reveal>

      <div className="mt-12 grid gap-6 md:grid-cols-2">
        {SOLUTIONS.map((s, i) => (
          <Reveal key={s.title} delay={i * 0.06}>
            <Card className="h-full">
              <CardHeader>
                <s.icon className="h-8 w-8 text-teal" />
                <CardTitle className="mt-3">{s.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-neutral-900/70 dark:text-white/70">{s.problem}</p>
                <ul className="mt-4 space-y-1.5 text-sm text-neutral-900/70 dark:text-white/70">
                  {s.capabilities.map((c) => (
                    <li key={c} className="flex gap-2">
                      <span className="text-teal">&bull;</span>
                      {c}
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-sm font-medium text-navy dark:text-white">{s.outcomes}</p>
              </CardContent>
            </Card>
          </Reveal>
        ))}
      </div>

      <Reveal className="mx-auto mt-20 max-w-2xl">
        <h2 className="text-center font-serif text-2xl font-semibold text-navy dark:text-white">
          Frequently asked questions
        </h2>
        <Accordion type="single" collapsible className="mt-6">
          {FAQ.map((item) => (
            <AccordionItem key={item.q} value={item.q}>
              <AccordionTrigger>{item.q}</AccordionTrigger>
              <AccordionContent>{item.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </Reveal>
    </div>
  );
}
