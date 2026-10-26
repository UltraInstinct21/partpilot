import { cn } from "@/lib/utils";

export interface PartPilotLogoProps {
  size?: number;
  className?: string;
  showWordmark?: boolean;
  wordmarkClassName?: string;
}

/**
 * Minimalist PartPilot Brand Emblem.
 * Pure vector geometry: A dual-facet supersonic pilot vector with a semiconductor gate channel.
 * Minimal, crisp, containerless.
 */
export function PartPilotLogo({
  size = 24,
  className,
  showWordmark = false,
  wordmarkClassName,
}: PartPilotLogoProps) {
  const mark = (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width: size, height: size }}
      className={cn(
        "shrink-0 select-none transition-transform duration-200 group-hover:scale-105 group-hover:-translate-y-0.5",
        className,
      )}
      role="img"
      aria-label="PartPilot Logo"
    >
      {/* Left Wing - Direct Light Facet */}
      <path
        d="M11 3.5L3.5 20.5L11 16.5V3.5Z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeLinejoin="round"
        className="text-white"
      />
      {/* Right Wing - Dimensional Shadow Facet */}
      <path
        d="M13 3.5L20.5 20.5L13 16.5V3.5Z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeLinejoin="round"
        className="text-zinc-400 group-hover:text-zinc-300 transition-colors"
      />
    </svg>
  );

  if (!showWordmark) {
    return mark;
  }

  return (
    <div className="flex items-center gap-2.5">
      {mark}
      <span
        className={cn(
          "font-heading text-base sm:text-lg font-medium tracking-tight text-white flex items-center",
          wordmarkClassName,
        )}
      >
        Part<span className="font-normal text-zinc-400">Pilot</span>
      </span>
    </div>
  );
}
