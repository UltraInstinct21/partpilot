import { useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, Scale, Search, WifiOff, HelpCircle } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useCompareSelection } from "@/lib/compare-store";
import { useReviewQueueStore } from "@/lib/review-queue-store";
import { CommandPalette } from "@/components/command-palette";
import { KeyboardShortcutsDialog } from "@/components/keyboard-shortcuts";
import { GlassSurface } from "@/components/react-bits/GlassSurface";
import { PartPilotLogo } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/search", label: "Find parts" },
  { href: "/compare", label: "Compare" },
  { href: "/bom", label: "BOM risk" },
  { href: "/review", label: "Review queue" },
  { href: "/dashboard", label: "Activity" },
];

export function AppNav() {
  const location = useLocation();
  const { selectedParts } = useCompareSelection();
  const { totalCount: reviewCount } = useReviewQueueStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [scrolled, setScrolled] = useState(() => (typeof window !== "undefined" ? window.scrollY > 20 : false));
  const [scrollProgress, setScrollProgress] = useState(0);

  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY;
      setScrolled(scrollY > 20);

      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      if (maxScroll > 0) {
        setScrollProgress(Math.min(100, Math.max(0, (scrollY / maxScroll) * 100)));
      }
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Keyboard navigation shortcuts
  useEffect(() => {
    let gPressed = false;
    let gTimeout: ReturnType<typeof setTimeout>;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts if focus is inside an input, textarea or select
      const activeEl = document.activeElement;
      const isInput =
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement ||
        activeEl instanceof HTMLSelectElement ||
        activeEl?.getAttribute("contenteditable") === "true";

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((prev) => !prev);
        return;
      }

      if (isInput) return;

      if (e.key === "/") {
        e.preventDefault();
        const searchInput =
          document.getElementById("search-input") ||
          document.querySelector("input[type='search']") ||
          document.querySelector("input");
        if (searchInput instanceof HTMLInputElement) {
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen(true);
        return;
      }

      if (e.key.toLowerCase() === "g") {
        gPressed = true;
        clearTimeout(gTimeout);
        gTimeout = setTimeout(() => {
          gPressed = false;
        }, 1000);
        return;
      }

      if (gPressed) {
        gPressed = false;
        const key = e.key.toLowerCase();
        if (key === "s") window.location.href = "/search";
        else if (key === "c") window.location.href = "/compare";
        else if (key === "b") window.location.href = "/bom";
        else if (key === "r") window.location.href = "/review";
        else if (key === "j") window.location.href = "/jobs";
        else if (key === "d") window.location.href = "/dashboard";
        else if (key === "h") window.location.href = "/";
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      clearTimeout(gTimeout);
    };
  }, []);

  return (
    <>
      {/* Skip to Content Accessibility Link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-[4px] focus:bg-white focus:px-4 focus:py-2 focus:text-black focus:font-medium focus:outline-2 focus:outline-white"
      >
        Skip to main content
      </a>

      {/* Offline Alert Banner */}
      {isOffline && (
        <div
          role="alert"
          className="fixed top-0 inset-x-0 z-[60] bg-zinc-800 border-b border-white/20 px-4 py-1.5 text-center text-xs text-white font-mono flex items-center justify-center gap-2"
        >
          <WifiOff className="size-3.5 text-zinc-400" />
          <span>
            You are currently offline. Cached data remains available, but searches and live checks will fail.
          </span>
        </div>
      )}

      {/* Scroll Progress Hairline Indicator themed to the site */}
      <div
        aria-hidden="true"
        className="fixed top-0 inset-x-0 h-[2px] z-[70] pointer-events-none transition-opacity duration-300"
        style={{ opacity: scrolled ? 1 : 0 }}
      >
        <div
          className="h-full bg-gradient-to-r from-zinc-500 via-white to-zinc-400 transition-all duration-75 ease-out"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      {/* Adaptive Topbar: full-width bar at top → floating dock on scroll */}
      <header
        role="banner"
        className={cn(
          "fixed inset-x-0 z-50 flex justify-center pointer-events-none transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]",
          isOffline ? "top-10" : scrolled ? "top-3 sm:top-4" : "top-0",
          scrolled ? "px-3 sm:px-6" : "px-0",
        )}
      >
        <div
          className={cn(
            "pointer-events-auto transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]",
            scrolled ? "w-full max-w-7xl" : "w-full max-w-full",
          )}
        >
          <GlassSurface
            width="100%"
            height={scrolled ? 56 : 64}
            borderRadius={scrolled ? 28 : 0}
            distortionScale={-180}
            displace={0.4}
            backgroundOpacity={scrolled ? 0.12 : 0.05}
            blur={scrolled ? 11 : 14}
            brightness={50}
            className={cn(
              "w-full shadow-none transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]",
              scrolled
                ? "border border-white/15 px-3.5 sm:px-6"
                : "border-b border-white/10 border-x-0 border-t-0 px-4 sm:px-8 lg:px-12",
            )}
          >
            <div className="flex w-full items-center justify-between gap-2 sm:gap-4">
              {/* Left: Brand Emblem & Wordmark */}
              <div className="flex items-center gap-6">
                <Link
                  to="/"
                  className="flex items-center gap-2 group text-white select-none transition-opacity hover:opacity-90"
                  aria-label="PartPilot Home"
                >
                  <PartPilotLogo size={22} />
                  <span className="font-heading text-base sm:text-lg font-semibold tracking-tight text-white flex items-center">
                    Part<span className="font-normal text-zinc-400">Pilot</span>
                  </span>
                </Link>
              </div>

              {/* Center: Nav links */}
              <nav
                role="navigation"
                aria-label="Main"
                className="hidden lg:flex items-center gap-1"
              >
                {NAV_LINKS.map((link) => {
                  const isActive =
                    location.pathname === link.href ||
                    (link.href !== "/" && location.pathname.startsWith(link.href));
                  const isReview = link.href === "/review";
                  return (
                    <Link
                      key={link.href}
                      to={link.href}
                      className={cn(
                        "rounded-full px-3.5 py-1 text-xs font-medium transition-all select-none inline-flex items-center gap-1.5",
                        isActive
                          ? "text-white bg-white/20 font-semibold"
                          : "text-zinc-400 hover:text-white hover:bg-white/10",
                      )}
                    >
                      <span>{link.label}</span>
                      {isReview && reviewCount > 0 && (
                        <span className="rounded-full bg-white/15 text-white border border-white/25 px-1.5 py-0.2 text-[10px] font-mono font-semibold">
                          {reviewCount}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </nav>

              {/* Right: Search, Compare, Shortcuts & Mobile Menu */}
              <div className="flex items-center gap-2">
                {/* Command Palette Trigger Button */}
                <button
                  type="button"
                  onClick={() => setCmdOpen(true)}
                  aria-label="Open command palette"
                  className="hidden sm:inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-3.5 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-white transition"
                >
                  <Search className="size-3.5 text-zinc-400" />
                  <span>Search...</span>
                  <kbd className="rounded-[4px] border border-white/20 px-1.5 py-0.2 text-[10px] font-mono text-zinc-300">
                    ⌘K
                  </kbd>
                </button>

                {/* Compare Tray Button */}
                <Link
                  to="/compare"
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition",
                    selectedParts.length > 0
                      ? "border-white bg-white/20 text-white"
                      : "border-white/15 bg-white/[0.04] text-zinc-300 hover:text-white hover:bg-white/10",
                  )}
                  title="View component comparison"
                >
                  <Scale className="size-3.5" />
                  <span className="hidden sm:inline">Compare</span>
                  {selectedParts.length > 0 && (
                    <span className="rounded-full bg-white px-1.5 py-0.2 font-mono text-[10px] font-bold text-black">
                      {selectedParts.length}
                    </span>
                  )}
                </Link>

                {/* Shortcuts Help Icon Button */}
                <button
                  type="button"
                  onClick={() => setShortcutsOpen(true)}
                  title="Keyboard shortcuts (?)"
                  aria-label="View keyboard shortcuts"
                  className="rounded-full border border-white/15 bg-white/[0.04] p-1.5 text-zinc-300 hover:text-white hover:bg-white/10 transition focus-visible:outline-2 focus-visible:outline-white"
                >
                  <HelpCircle className="size-4" />
                </button>

                {/* Mobile Navigation Menu Trigger */}
                <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                  <SheetTrigger asChild>
                    <button
                      type="button"
                      aria-label="Open navigation menu"
                      className="lg:hidden rounded-full border border-white/15 bg-white/[0.04] p-2 text-white hover:bg-white/10"
                    >
                      <Menu className="size-5" />
                    </button>
                  </SheetTrigger>
                  <SheetContent side="right" className="w-64 bg-[#121215] text-white border-l border-white/10 p-6 rounded-l-[12px] shadow-none">
                    <SheetHeader className="p-0 border-0 mb-6">
                      <SheetTitle className="text-left flex items-center gap-2 text-white">
                        <PartPilotLogo size={22} />
                        <span className="font-heading text-lg font-semibold tracking-tight text-white flex items-center">
                          Part<span className="font-normal text-zinc-400">Pilot</span>
                        </span>
                      </SheetTitle>
                    </SheetHeader>
                    <nav className="flex flex-col gap-2">
                      <Link
                        to="/"
                        onClick={() => setMobileOpen(false)}
                        className="rounded-[8px] px-3 py-2 text-sm font-medium text-zinc-300 hover:text-white hover:bg-white/10"
                      >
                        Home
                      </Link>
                      {NAV_LINKS.map((link) => (
                        <Link
                          key={link.href}
                          to={link.href}
                          onClick={() => setMobileOpen(false)}
                          className="rounded-[8px] px-3 py-2 text-sm font-medium text-zinc-300 hover:text-white hover:bg-white/10 flex items-center justify-between"
                        >
                          <span>{link.label}</span>
                          {link.href === "/review" && reviewCount > 0 && (
                            <span className="rounded-full bg-white/15 text-white border border-white/25 px-2 py-0.5 text-xs font-mono font-semibold">
                              {reviewCount}
                            </span>
                          )}
                        </Link>
                      ))}
                    </nav>
                  </SheetContent>
                </Sheet>
              </div>
            </div>
          </GlassSurface>
        </div>
      </header>

      {/* Global Command Palette Dialog */}
      <CommandPalette open={cmdOpen} onOpenChange={setCmdOpen} />

      {/* Keyboard Shortcuts Sheet */}
      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </>
  );
}
