import { useState, useTransition } from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import { Search, Scale, FileSpreadsheet, CheckSquare, Activity, LayoutDashboard, Home, ArrowRight, Keyboard } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useParts } from "@/api/hooks";
import { useCompareSelection } from "@/lib/compare-store";
import { AnimatedList } from "@/components/react-bits/AnimatedList";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const { selectedParts, clear } = useCompareSelection();
  const [, startTransition] = useTransition();

  // Search parts by MPN
  const partsQuery = useParts({ q: query, limit: 6 });
  const searchResults = query.trim().length > 0 ? partsQuery.data?.results ?? [] : [];

  const handleSelect = (callback: () => void) => {
    onOpenChange(false);
    startTransition(() => {
      callback();
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 max-w-xl overflow-hidden rounded-[12px] border border-white/15 bg-[#121215] text-white shadow-none">
        <DialogTitle className="sr-only">Command Palette</DialogTitle>
        <Command
          className="w-full flex flex-col overflow-hidden text-sm"
          loop
        >
          {/* Search Input */}
          <div className="flex items-center border-b border-white/10 px-4 py-3">
            <Search className="size-4 text-zinc-400 mr-2 shrink-0" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Search MPN or type a command (e.g. 'go to compare')..."
              className="w-full bg-transparent font-sans text-sm text-white placeholder:text-zinc-500 outline-none"
            />
          </div>

          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="p-4 text-center text-xs text-zinc-400 font-mono">
              No matching commands or components found.
            </Command.Empty>

            {/* Matching Components */}
            {searchResults.length > 0 && (
              <div className="px-2 py-1 border-b border-white/10">
                <div className="text-[11px] font-mono uppercase text-zinc-400 px-2 py-1 font-bold">
                  Matched Parts ({searchResults.length})
                </div>
                <AnimatedList
                  items={searchResults.map((part) => ({
                    id: part.part_id,
                    title: part.mpn,
                    description: `${part.manufacturer} (${part.family})`,
                    meta: "Select",
                  }))}
                  onItemSelect={(item) => {
                    const id = (item as any).id;
                    handleSelect(() => navigate(`/parts/${id}`));
                  }}
                  animation="pop"
                  theme="dark"
                  width="100%"
                  maxHeight={200}
                  frame={false}
                />
              </div>
            )}

            {/* Navigation Commands */}
            <Command.Group heading="Navigation" className="text-[11px] font-mono uppercase text-zinc-400 px-2 py-1.5 font-bold">
              <Command.Item
                value="home"
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <Home className="size-3.5 text-zinc-400" />
                <span>Go to Home</span>
              </Command.Item>
              <Command.Item
                value="search"
                onSelect={() => handleSelect(() => navigate("/search"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <Search className="size-3.5 text-zinc-400" />
                <span>Go to Parametric Search</span>
              </Command.Item>
              <Command.Item
                value="compare"
                onSelect={() => handleSelect(() => navigate("/compare"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <Scale className="size-3.5 text-zinc-400" />
                <span>Go to Component Compare</span>
              </Command.Item>
              <Command.Item
                value="bom"
                onSelect={() => handleSelect(() => navigate("/bom"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <FileSpreadsheet className="size-3.5 text-zinc-400" />
                <span>Go to BOM Risk Check</span>
              </Command.Item>
              <Command.Item
                value="review"
                onSelect={() => handleSelect(() => navigate("/review"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <CheckSquare className="size-3.5 text-zinc-400" />
                <span>Go to Review Queue</span>
              </Command.Item>
              <Command.Item
                value="jobs"
                onSelect={() => handleSelect(() => navigate("/jobs"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <Activity className="size-3.5 text-zinc-400" />
                <span>Go to Extraction Jobs</span>
              </Command.Item>
              <Command.Item
                value="dashboard"
                onSelect={() => handleSelect(() => navigate("/dashboard"))}
                className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
              >
                <LayoutDashboard className="size-3.5 text-zinc-400" />
                <span>Go to Dashboard</span>
              </Command.Item>
            </Command.Group>

            {/* Compare Actions */}
            {selectedParts.length > 0 && (
              <Command.Group heading="Compare Tray" className="text-[11px] font-mono uppercase text-zinc-400 px-2 py-1.5 font-bold">
                <Command.Item
                  value="open compare tray"
                  onSelect={() => handleSelect(() => navigate(`/compare?ids=${selectedParts.map((p) => p.id).join(",")}`))}
                  className="flex items-center justify-between rounded-[4px] px-3 py-2 text-xs text-zinc-200 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
                >
                  <div className="flex items-center gap-2">
                    <Scale className="size-3.5 text-zinc-400" />
                    <span>Compare {selectedParts.length} selected parts</span>
                  </div>
                  <ArrowRight className="size-3.5" />
                </Command.Item>
                <Command.Item
                  value="clear compare tray"
                  onSelect={() => handleSelect(() => clear())}
                  className="flex items-center gap-2 rounded-[4px] px-3 py-2 text-xs text-zinc-400 cursor-pointer hover:bg-white/10 aria-selected:bg-white/15 select-none"
                >
                  <span>Clear compare tray selection</span>
                </Command.Item>
              </Command.Group>
            )}
          </Command.List>

          <div className="border-t border-white/10 px-4 py-2 flex items-center justify-between text-[11px] font-mono text-zinc-400 bg-black/40">
            <span className="flex items-center gap-1.5">
              <Keyboard className="size-3" />
              Use ↑↓ to navigate, Enter to select, Esc to close
            </span>
            <span>Cmd+K</span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
