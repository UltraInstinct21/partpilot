import { useState } from "react";
import { Copy, Check, AlertTriangle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatParameterValue, formatCondition } from "@/lib/format";
import type { ParameterValue } from "@/api/hooks";
import { cn } from "@/lib/utils";

export interface ParamValueProps {
  param: ParameterValue;
  apiValue?: string | number | null;
  showCondition?: boolean;
  showCopy?: boolean;
  className?: string;
}

/**
 * Renders an extracted parameter value with unit, measurement condition,
 * datasheet vs API disagreement indicator, and a copy button.
 */
export function ParamValue({
  param,
  apiValue,
  showCondition = true,
  showCopy = true,
  className,
}: ParamValueProps) {
  const [copied, setCopied] = useState(false);

  const formattedValue = formatParameterValue(param);
  const conditionText = formatCondition(param.condition);

  // Check for disagreement between extracted datasheet value and distributor API value
  const hasDisagreement =
    apiValue !== undefined &&
    apiValue !== null &&
    String(apiValue).trim() !== "" &&
    String(apiValue).trim() !== String(param.value).trim() &&
    String(apiValue).trim() !== formattedValue.trim();

  const handleCopy = () => {
    const textToCopy = `${param.name}: ${formattedValue}${conditionText ? ` (${conditionText})` : ""}`;
    navigator.clipboard.writeText(textToCopy).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={cn("inline-flex flex-col gap-0.5", className)}>
      <div className="inline-flex items-center gap-1.5 font-mono text-sm text-ink">
        <span className="font-medium text-[14px]">{formattedValue}</span>

        {/* Datasheet vs API Disagreement marker with tooltip */}
        {hasDisagreement && (
          <TooltipProvider delayDuration={100}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  role="img"
                  aria-label="Disagreement with distributor API value"
                  className="cursor-help inline-flex items-center text-ink hover:text-black"
                >
                  <AlertTriangle className="size-3.5 stroke-[2]" />
                </span>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                className="rounded-[4px] border border-ink/20 bg-haze text-ink p-2 text-xs shadow-none max-w-xs"
              >
                <div className="font-semibold mb-1">Value Discrepancy</div>
                <div>Datasheet extracted: <span className="font-mono">{formattedValue}</span></div>
                <div>Distributor API reported: <span className="font-mono">{String(apiValue)}</span></div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Copy button */}
        {showCopy && formattedValue !== "-" && (
          <button
            type="button"
            onClick={handleCopy}
            title="Copy value"
            aria-label="Copy parameter value"
            className="p-0.5 text-ink/50 hover:text-ink transition-none rounded-[2px]"
          >
            {copied ? <Check className="size-3 text-ink" /> : <Copy className="size-3" />}
          </button>
        )}
      </div>

      {/* Measurement Condition */}
      {showCondition && conditionText && (
        <span className="text-[12px] text-ink/60 font-sans leading-tight">
          {conditionText}
        </span>
      )}
    </div>
  );
}
