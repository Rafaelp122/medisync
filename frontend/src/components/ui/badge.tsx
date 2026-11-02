import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
        warning: "border-transparent bg-amber-500 text-white shadow-sm",
        success: "border-transparent bg-emerald-600 text-white shadow-sm",
        nivel1: "border-transparent bg-red-600 text-white shadow-sm",
        nivel2: "border-transparent bg-orange-600 text-white shadow-sm",
        nivel3: "border-transparent bg-yellow-400 text-yellow-950 font-bold shadow-sm",
        nivel4: "border-transparent bg-emerald-600 text-white shadow-sm",
        nivel5: "border-transparent bg-blue-600 text-white shadow-sm",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  ref?: React.Ref<HTMLDivElement>;
}

export function Badge({ className, variant, ref, ...props }: BadgeProps) {
  return <div ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
