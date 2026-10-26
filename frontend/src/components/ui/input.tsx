import * as React from "react"
import { cn } from "cn"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "w-full min-w-0 rounded-[4px] border border-white/15 bg-haze px-3 py-2 text-base text-ink transition-none outline-none placeholder:text-zinc-500 focus-visible:outline-2 focus-visible:outline-white focus-visible:outline-offset-1 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40 md:text-sm shadow-none",
        className
      )}
      {...props}
    />
  )
}

export { Input }
