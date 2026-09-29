import { cn } from "@/lib/utils";

/** Stands in for photography/screenshots (Phase 7 imagery pipeline is out of
 * scope for this build): a labelled gradient panel so layouts read
 * correctly without downloaded stock assets. */
export function GradientVisual({
  label,
  className,
  variant = "navy",
}: {
  label: string;
  className?: string;
  variant?: "navy" | "teal";
}) {
  const gradient =
    variant === "navy"
      ? "from-navy via-deep-blue to-teal"
      : "from-teal via-deep-blue to-navy";
  return (
    <div
      className={cn(
        `flex items-center justify-center rounded-card bg-gradient-to-br ${gradient} p-8 text-center text-sm font-medium text-white/80`,
        className,
      )}
      role="img"
      aria-label={label}
    >
      {label}
    </div>
  );
}
