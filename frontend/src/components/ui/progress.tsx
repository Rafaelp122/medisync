import type * as React from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;
  max?: number;
  indicatorClassName?: string;
  ref?: React.Ref<HTMLDivElement>;
}

export function Progress({
  className,
  value = 0,
  max = 100,
  indicatorClassName,
  ref,
  ...props
}: ProgressProps) {
  const percentage = Math.min(Math.max(0, (value / (max || 100)) * 100), 100);

  return (
    <div
      ref={ref}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn("relative h-3 w-full overflow-hidden rounded-full bg-muted", className)}
      {...props}
    >
      <div
        className={cn(
          "h-full w-full flex-1 bg-primary transition-transform duration-300 ease-in-out motion-reduce:transition-none",
          indicatorClassName,
        )}
        style={{ transform: `translateX(-${100 - percentage}%)` }}
      />
    </div>
  );
}
