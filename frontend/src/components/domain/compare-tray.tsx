import { useNavigate } from "react-router-dom";
import { X, Scale } from "lucide-react";
import { useCompareSelection } from "@/lib/compare-store";
import { cn } from "@/lib/utils";

/**
 * Persistent bottom compare bar when 1 or more parts are selected.
 * Shows part names (max 4), a Clear button (Ghost), and Compare button (Haze).
 */
export function CompareTray() {
  const { selectedParts, removePart, clear } = useCompareSelection();
  const navigate = useNavigate();

  if (selectedParts.length === 0) {
    return null;
  }

  const handleCompare = () => {
    const ids = selectedParts.map((p) => p.id).join(",");
    navigate(`/compare?ids=${ids}`);
  };

  return (
    <aside
      aria-label="Component comparison tray"
      className="fixed bottom-0 inset-x-0 z-40 border-t border-white/20 bg-black/95 backdrop-blur-none py-3 px-4 transition-none"
    >
      <div className="w-full px-4 sm:px-6 lg:px-8 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider font-mono text-zinc-400 mr-2">
            <Scale className="size-4 text-white" />
            <span>Compare ({selectedParts.length}/4):</span>
          </div>

          {selectedParts.map((part) => (
            <div
              key={part.id}
              className="inline-flex items-center gap-1.5 rounded-[4px] border border-white/20 bg-white/5 px-2.5 py-1 text-xs font-mono text-white select-none"
            >
              <span>{part.mpn}</span>
              <button
                type="button"
                onClick={() => removePart(part.id)}
                aria-label={`Remove ${part.mpn} from compare`}
                className="text-zinc-400 hover:text-white transition-none ml-0.5"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={clear}
            className="rounded-[8px] border border-white/20 bg-transparent px-3 py-1.5 text-xs font-medium text-white hover:bg-white/10 active:bg-white/15 focus-visible:outline-2 focus-visible:outline-white transition-none"
          >
            Clear
          </button>

          <button
            type="button"
            onClick={handleCompare}
            disabled={selectedParts.length < 2}
            title={selectedParts.length < 2 ? "Select at least 2 parts to compare" : "Compare parts side by side"}
            className={cn(
              "rounded-[8px] border border-white bg-white px-4 py-1.5 text-xs font-medium text-black hover:bg-zinc-200 active:bg-zinc-300 focus-visible:outline-2 focus-visible:outline-white transition-none shadow-none disabled:opacity-40 disabled:pointer-events-none",
            )}
          >
            Compare ({selectedParts.length})
          </button>
        </div>
      </div>
    </aside>
  );
}
