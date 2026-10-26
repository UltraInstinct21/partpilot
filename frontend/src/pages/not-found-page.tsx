import { Link } from "react-router-dom";
import { Search } from "lucide-react";

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center px-4 w-full">
      <div className="rounded-[12px] bg-[#121215] text-white p-8 max-w-md w-full border border-white/10 shadow-none">
        <div className="font-mono text-3xl font-bold mb-2">404</div>
        <h1 className="font-heading text-xl font-medium text-white mb-2">Page not found</h1>
        <p className="text-xs text-zinc-400 mb-6">
          The requested address does not match any route in PartPilot.
        </p>
        <Link
          to="/search"
          className="inline-flex items-center justify-center gap-2 rounded-[8px] border border-white bg-white px-4 py-2 text-xs font-medium text-black hover:bg-zinc-200 transition-none"
        >
          <Search className="size-3.5" />
          <span>Go to parametric search</span>
        </Link>
      </div>
    </div>
  );
}
