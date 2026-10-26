import { useState, useEffect } from "react";
import {
  MotionGrid,
  MotionGridCells,
  type Frames,
} from "@animate-ui/react/primitives/motion-grid";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

// Standard ripple frame cycle: center -> orthogonal -> corners -> reset
const DEFAULT_MOTION_GRID_FRAMES: Frames = [
  [[1, 1]],
  [
    [0, 1],
    [1, 0],
    [1, 2],
    [2, 1],
  ],
  [
    [0, 0],
    [0, 2],
    [2, 0],
    [2, 2],
  ],
  [],
];

export interface MotionGridLoaderProps {
  gridSize?: [number, number];
  frames?: Frames;
  duration?: number;
  size?: "xs" | "sm" | "md" | "lg";
  variant?: "default" | "white" | "muted";
  className?: string;
  dotClassName?: string;
}

const SIZE_MAP = {
  xs: {
    grid: "gap-0.5",
    dot: "size-1 rounded-full",
  },
  sm: {
    grid: "gap-1",
    dot: "size-1.5 rounded-full",
  },
  md: {
    grid: "gap-1.5",
    dot: "size-2 rounded-full",
  },
  lg: {
    grid: "gap-2",
    dot: "size-2.5 rounded-full",
  },
};

const VARIANT_MAP = {
  default: "bg-foreground/20 data-[active=true]:bg-foreground transition-colors duration-150",
  white: "bg-white/20 data-[active=true]:bg-white transition-colors duration-150",
  muted: "bg-white/10 data-[active=true]:bg-white/70 transition-colors duration-150",
};

/**
 * Animated Motion Grid Loader primitive based on @animate-ui/react motion-grid.
 * Strictly monochrome (neutral white/foreground tints).
 */
export function MotionGridLoader({
  gridSize = [3, 3],
  frames = DEFAULT_MOTION_GRID_FRAMES,
  duration = 200,
  size = "sm",
  variant = "default",
  className,
  dotClassName,
}: MotionGridLoaderProps) {
  const sizeConfig = SIZE_MAP[size];
  const variantConfig = VARIANT_MAP[variant] || VARIANT_MAP.default;

  return (
    <MotionGrid
      gridSize={gridSize}
      frames={frames}
      duration={duration}
      className={cn("inline-grid select-none shrink-0", sizeConfig.grid, className)}
      aria-hidden="true"
    >
      <MotionGridCells className={cn(sizeConfig.dot, variantConfig, dotClassName)} />
    </MotionGrid>
  );
}

export interface ProgressLoadingStateProps {
  title?: string;
  description?: string;
  /** When provided, displays determinate progress (0 to 100). When omitted or null, runs simulated progress. */
  progress?: number | null;
  /** Sequence of stage messages to cycle through during indeterminate progress. */
  stages?: string[];
  size?: "sm" | "md" | "lg";
  variant?: "default" | "white" | "muted";
  className?: string;
  showProgressBar?: boolean;
  showPercentage?: boolean;
}

const DEFAULT_STAGES = [
  "Initializing query parameters…",
  "Resolving datasheet cross-references…",
  "Aggregating parametric specifications…",
  "Finalizing record synthesis…",
];

/**
 * Rich loading state with Motion Grid animation and monochrome progress update UI elements.
 */
export function ProgressLoadingState({
  title = "Loading data…",
  description,
  progress: explicitProgress,
  stages = DEFAULT_STAGES,
  size = "md",
  variant = "default",
  className,
  showProgressBar = true,
  showPercentage = true,
}: ProgressLoadingStateProps) {
  const isDeterminate = explicitProgress !== undefined && explicitProgress !== null;

  // For indeterminate loading, simulate progressive stages to provide reassuring visual feedback
  const [simulatedProgress, setSimulatedProgress] = useState(12);
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    if (isDeterminate) return;

    const progressTimer = setInterval(() => {
      setSimulatedProgress((prev) => {
        if (prev >= 94) return prev;
        // Asymptotically slow down as it gets closer to 95%
        const increment = Math.max(1, Math.round((95 - prev) * 0.12));
        return Math.min(94, prev + increment);
      });
    }, 450);

    const stageTimer = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % stages.length);
    }, 2400);

    return () => {
      clearInterval(progressTimer);
      clearInterval(stageTimer);
    };
  }, [isDeterminate, stages.length]);

  const currentPercent = isDeterminate
    ? Math.min(100, Math.max(0, Math.round(explicitProgress!)))
    : simulatedProgress;

  const currentStageText = description ?? (isDeterminate ? null : stages[stageIndex]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "rounded-[16px] border border-white/10 bg-white/[0.02] backdrop-blur-xl p-6 text-white space-y-4",
        className
      )}
    >
      <div className="flex items-start gap-4">
        <div className="mt-1 flex size-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
          <MotionGridLoader size={size === "lg" ? "md" : "sm"} variant={variant} />
        </div>

        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-heading text-sm font-medium text-white truncate">{title}</h4>
            {showPercentage && (
              <span className="font-mono text-xs font-semibold text-zinc-300 shrink-0">
                {currentPercent}%
              </span>
            )}
          </div>
          {currentStageText && (
            <p className="text-xs text-zinc-400 font-sans transition-all duration-300">
              {currentStageText}
            </p>
          )}
        </div>
      </div>

      {showProgressBar && (
        <div className="space-y-1.5">
          <Progress
            value={currentPercent}
            className="h-1.5 bg-white/10 overflow-hidden"
          />
          <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
            <span>Progress update</span>
            <span>{isDeterminate ? "Live stream" : "Optimizing results"}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export interface InlineProgressLoaderProps {
  label: string;
  progress?: number | null;
  variant?: "default" | "white" | "muted";
  className?: string;
  showBar?: boolean;
}

/**
 * Compact inline loader with monochrome Motion Grid and progress update UI.
 */
export function InlineProgressLoader({
  label,
  progress,
  variant = "default",
  className,
  showBar = true,
}: InlineProgressLoaderProps) {
  const isDeterminate = progress !== undefined && progress !== null;
  const [indeterminateProgress, setIndeterminateProgress] = useState(20);

  useEffect(() => {
    if (isDeterminate) return;
    const interval = setInterval(() => {
      setIndeterminateProgress((p) => (p >= 92 ? 20 : p + 8));
    }, 400);
    return () => clearInterval(interval);
  }, [isDeterminate]);

  const value = isDeterminate ? Math.round(progress!) : indeterminateProgress;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("flex items-center gap-3 text-xs font-mono text-zinc-300", className)}
    >
      <MotionGridLoader size="xs" variant={variant} />
      <span className="truncate">{label}</span>
      {showBar && (
        <div className="flex items-center gap-2 ml-auto shrink-0">
          <div className="h-1 w-24 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full bg-white transition-all duration-300 rounded-full"
              style={{ width: `${value}%` }}
            />
          </div>
          <span className="text-[10px] text-zinc-400 w-8 text-right">{value}%</span>
        </div>
      )}
    </div>
  );
}
