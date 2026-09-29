const CONTENT: Record<string, { title: string; body: string }> = {
  privacy: {
    title: "Privacy Policy",
    body: "This demo environment processes only synthetic and self-supplied data. In a production deployment, this page would describe what personal data SentinelKYC collects, why, retention periods, and data subject rights.",
  },
  terms: {
    title: "Terms of Service",
    body: "This demo environment is provided for evaluation only, with no uptime or support commitments. A production Terms of Service would cover acceptable use, liability and subscription terms.",
  },
  cookies: {
    title: "Cookie Policy",
    body: "This site uses only strictly necessary cookies to remember your cookie-consent choice. No third-party advertising or analytics cookies are set in this demo environment.",
  },
};

export default function LegalStub({ slug }: { slug: string }) {
  const entry = CONTENT[slug] ?? { title: "Legal", body: "Content not found." };
  return (
    <div className="container max-w-2xl py-16 md:py-24">
      <h1 className="font-serif text-3xl font-semibold text-navy dark:text-white">
        {entry.title}
      </h1>
      <p className="mt-4 text-neutral-900/70 dark:text-white/70">{entry.body}</p>
    </div>
  );
}
