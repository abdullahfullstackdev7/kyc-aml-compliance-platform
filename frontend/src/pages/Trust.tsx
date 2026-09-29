import { Lock, KeyRound, GitBranch, Globe2, Bug, Building } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal } from "@/components/Reveal";

const SECTIONS = [
  {
    icon: Lock,
    title: "Encryption",
    body: "Customer PII (name, date of birth, address) is encrypted at rest with AES-256-GCM using per-tenant, versioned data encryption keys. Key rotation re-wraps keys without re-encrypting historical ciphertext.",
  },
  {
    icon: KeyRound,
    title: "Access control",
    body: "Role-based and attribute-based access control (same-tenant, four-eyes, case-assignment checks) gates every case action. Staff accounts require mandatory TOTP multi-factor authentication.",
  },
  {
    icon: GitBranch,
    title: "Audit integrity",
    body: "Every state transition, decision and login is written to an append-only, hash-chained audit log. The chain is verified per tenant, and a database trigger blocks UPDATE/DELETE on audit rows even for a superuser.",
  },
  {
    icon: Globe2,
    title: "Data residency",
    body: "This demo environment runs a single-region PostgreSQL deployment. Production deployments can be region-pinned per tenant; contact sales for residency commitments.",
  },
  {
    icon: Bug,
    title: "Responsible disclosure",
    body: "If you believe you've found a security issue, email security@sentinelkyc.example with details and a way to reach you. We aim to acknowledge reports within two business days.",
  },
  {
    icon: Building,
    title: "Sub-processors",
    body: "Groq and Google (Gemini) are used, on their free tiers, only to draft case summaries and decision rationale for a human reviewer; they never make a screening or decision call. Payloads sent to them are pseudonymized.",
  },
];

export default function Trust() {
  return (
    <div className="container py-16 md:py-24" id="disclosure">
      <Reveal>
        <h1 className="font-serif text-4xl font-semibold text-navy dark:text-white">
          Trust Center
        </h1>
        <p className="mt-3 max-w-2xl text-lg text-neutral-900/70 dark:text-white/70">
          What actually protects your data, in plain terms.
        </p>
      </Reveal>

      <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {SECTIONS.map((s, i) => (
          <Reveal key={s.title} delay={i * 0.05}>
            <Card className="h-full">
              <CardHeader>
                <s.icon className="h-7 w-7 text-teal" />
                <CardTitle className="mt-3 text-base">{s.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-neutral-900/70 dark:text-white/70">
                {s.body}
              </CardContent>
            </Card>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
