import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full bg-teal/10 px-3 py-1 text-xs font-medium text-teal",
        className,
      )}
      {...props}
    />
  );
}
