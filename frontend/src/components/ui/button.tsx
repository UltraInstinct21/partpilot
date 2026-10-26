import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[8px] border text-sm font-medium whitespace-nowrap transition-none outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 shadow-none",
  {
    variants: {
      variant: {
        // Haze button (Primary action): Haze fill, Ink text, 1px Ink border
        default:
          "bg-haze text-ink border-ink/30 hover:bg-white active:bg-zinc-200 focus-visible:outline-ink",
        haze:
          "bg-haze text-ink border-ink/30 hover:bg-white active:bg-zinc-200 focus-visible:outline-ink",
        // Ghost button (Primary nav CTA): Transparent, 1px white border, white text
        ghost:
          "bg-transparent text-white border-white/20 hover:bg-white/10 active:bg-white/15 focus-visible:outline-white",
        outline:
          "bg-transparent text-white border-white/20 hover:bg-white/10 active:bg-white/15 focus-visible:outline-white",
        secondary:
          "bg-haze text-ink border-ink/20 hover:bg-white active:bg-zinc-200 focus-visible:outline-ink",
        destructive:
          "bg-transparent text-white border border-white/40 hover:bg-white/10 focus-visible:outline-white",
        link:
          "bg-transparent text-white underline underline-offset-4 border-0 p-0 hover:text-zinc-300 focus-visible:outline-white",
      },
      size: {
        default: "h-9 px-4 py-2 text-sm",
        sm: "h-7 px-3 text-xs",
        xs: "h-6 px-2 text-xs",
        lg: "h-11 px-5 text-base",
        icon: "size-9",
        "icon-sm": "size-7",
        "icon-xs": "size-6",
        "icon-lg": "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
