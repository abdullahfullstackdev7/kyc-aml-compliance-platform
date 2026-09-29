import { cn } from "@/lib/utils";

const TIER_STYLES: Record<string, string> = {
  clear: "bg-success-green/10 text-success-green",
  review: "bg-amber/10 text-amber",
  high_risk: "bg-risk-red/10 text-risk-red",
  reject: "bg-neutral-900/10 text-neutral-900 dark:bg-white/10 dark:text-white",
};

export function TierBadge({ tier }: { tier: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        TIER_STYLES[tier] ?? "bg-teal/10 text-teal",
      )}
    >
      {tier.replace("_", " ")}
    </span>
  );
}
