import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function ChartCard({
  title,
  description,
  loading,
  empty,
  error,
  children,
}: {
  title: string;
  description: string;
  loading?: boolean;
  empty?: boolean;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-semibold text-navy dark:text-white">{title}</h2>
          <span title={description}>
            <Info className="h-4 w-4 text-neutral-900/40 dark:text-white/40" />
          </span>
        </div>
        {error ? (
          <p className="mt-6 text-sm text-risk-red">{error}</p>
        ) : loading ? (
          <div className="mt-6 h-[280px] animate-pulse rounded-lg bg-neutral-900/5 dark:bg-white/5" />
        ) : empty ? (
          <p className="mt-6 text-sm text-neutral-900/50 dark:text-white/50">
            No data yet for this view.
          </p>
        ) : (
          <div className="mt-4">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}
