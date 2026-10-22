import { NavLink } from "react-router-dom";
import { CircuitBoard } from "lucide-react";
import { cn } from "@/lib/utils";

const LINKS = [
  { to: "/", label: "Search", end: true },
  { to: "/compare", label: "Compare", end: false },
  { to: "/bom", label: "BOM check", end: false },
  { to: "/review", label: "Review", end: false },
  { to: "/dashboard", label: "Dashboard", end: false },
];

/** The navigation bar of the application. */
export function AppNav() {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">
      <nav
        aria-label="Main"
        className="mx-auto flex h-14 max-w-[1280px] items-center gap-2 overflow-x-auto px-4"
      >
        <CircuitBoard aria-hidden className="size-5 shrink-0 text-primary" />
        <span className="shrink-0 text-base font-semibold tracking-tight">PartPilot</span>
        <div className="ml-4 flex items-center gap-1">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors whitespace-nowrap",
                  isActive
                    ? "bg-secondary text-secondary-foreground"
                    : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </header>
  );
}
