import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export interface KeyboardShortcutsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsProps) {
  const shortcuts = [
    { key: "/", desc: "Focus natural-language search bar" },
    { key: "Cmd + K / Ctrl + K", desc: "Open command palette and quick part search" },
    { key: "?", desc: "Show keyboard shortcuts sheet" },
    { key: "g then s", desc: "Navigate to Search" },
    { key: "g then c", desc: "Navigate to Compare" },
    { key: "g then b", desc: "Navigate to BOM Check" },
    { key: "g then r", desc: "Navigate to Review Queue" },
    { key: "g then j", desc: "Navigate to Extraction Jobs" },
    { key: "g then d", desc: "Navigate to Dashboard" },
    { key: "g then h", desc: "Navigate to Home" },
    { key: "j / k", desc: "Move selection down / up in tables and review queue" },
    { key: "Enter", desc: "Open selected row / accept decision" },
    { key: "a", desc: "Accept value in review panel" },
    { key: "c", desc: "Focus value correction field in review panel" },
    { key: "x", desc: "Reject value in review panel" },
    { key: "Esc", desc: "Close open Dialog, Sheet, or Source Viewer" },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md rounded-[12px] bg-[#121215] text-white p-6 border border-white/10 shadow-none">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold text-white">Keyboard Shortcuts</DialogTitle>
          <DialogDescription className="text-xs text-zinc-400">
            Keyboard navigation is active when not editing text fields.
          </DialogDescription>
        </DialogHeader>

        <div className="divide-y divide-white/10 mt-3 text-xs">
          {shortcuts.map((sc, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <span className="text-zinc-300">{sc.desc}</span>
              <kbd className="rounded-[4px] border border-white/15 bg-white/5 px-2 py-0.5 font-mono text-[11px] font-medium text-zinc-300">
                {sc.key}
              </kbd>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
