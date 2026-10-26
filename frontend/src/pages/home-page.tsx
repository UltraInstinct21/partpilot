import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { FileText, ShieldCheck, RefreshCw, Link, BarChart3 } from "lucide-react";
import { ScrollReveal } from "@/components/ui/scroll-reveal";
import { PartPilotLogo } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

const SAMPLE_QUERIES = [
  "100 V N-channel MOSFET, Rds(on) under 5 mΩ, in stock",
  "Automotive gate driver 4A peak current AEC-Q101",
  "Infineon SuperSO8 active N-channel",
  "60V MOSFET TO-220AB package low gate charge",
];

const HOW_IT_WORKS = [
  {
    title: "Ask in plain engineering language",
    desc: "Type a parametric need — voltage, current, package, compliance — and PartPilot resolves it against indexed datasheets.",
  },
  {
    title: "Every value is traced to its source",
    desc: "Click any specification to open the exact datasheet page, table, and test conditions it was extracted from.",
  },
  {
    title: "Verified before you use it",
    desc: "Three-tier validation rejects out-of-range figures, standardizes units, and flags discrepancies across sources.",
  },
];

const CAPABILITIES = [
  {
    icon: Link,
    title: "Every value links to its datasheet page",
    desc: "Click any specification to open the exact page, table, and test conditions extracted from the original PDF.",
  },
  {
    icon: ShieldCheck,
    title: "Values are checked before you see them",
    desc: "Three-tier validation rejects out-of-range figures, standardizes engineering units, and flags API discrepancies.",
  },
  {
    icon: RefreshCw,
    title: "Find replacements fast",
    desc: "Identify pin-compatible alternatives and drop-in equivalents ranked by electrical trade-offs and stock.",
  },
  {
    icon: Search,
    title: "Search in plain engineering language",
    desc: "Describe a part by its limits and conditions — no memorized part numbers or rigid filters required.",
  },
  {
    icon: FileText,
    title: "Verified against the original PDF",
    desc: "Every specification is anchored to the manufacturer datasheet page it was extracted from.",
  },
  {
    icon: BarChart3,
    title: "Stock-aware cross-references",
    desc: "Alternatives are ranked by electrical fit, distributor stock, and lead time from authorized sources.",
  },
];

interface FeatureCardProps {
  icon: React.ElementType;
  title: string;
  desc: string;
}

function FeatureCard({ icon: Icon, title, desc }: FeatureCardProps) {
  return (
    <div className="group space-y-3 transition-transform duration-300 hover:-translate-y-1 hover:scale-[1.01]">
      <Icon className="size-6 text-zinc-400 group-hover:text-white transition-colors duration-300" />
      <h3 className="font-heading text-lg font-medium text-white leading-snug">{title}</h3>
      <p className="text-sm text-zinc-400 leading-relaxed font-sans">{desc}</p>
    </div>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [scrolled, setScrolled] = useState(() =>
    typeof window !== "undefined" ? window.scrollY > 20 : false,
  );

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    navigate(`/search?q=${encodeURIComponent(trimmed)}`);
  };

  const handleSampleClick = (sample: string) => {
    setQuery(sample);
    navigate(`/search?q=${encodeURIComponent(sample)}`);
  };

  return (
    <div className="flex flex-col min-h-screen bg-black text-white w-full">
      {/* Full-Bleed Hero (viewport height) with gradient fade into black */}
      <section className="relative min-h-screen w-full flex flex-col justify-center px-4 sm:px-8 lg:px-12 pt-32 sm:pt-36 pb-20 border-b border-white/10 overflow-hidden">
        {/* Full-bleed photography from public/bg1.jpeg & public/bg2.jpeg */}
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat opacity-50 mix-blend-screen scale-105 pointer-events-none select-none"
          style={{ backgroundImage: "url('/bg1.jpeg')" }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat opacity-30 mix-blend-overlay pointer-events-none select-none"
          style={{ backgroundImage: "url('/bg2.jpeg')" }}
        />
        {/* Gradient that smoothly fades into the black canvas below the image */}
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 bg-gradient-to-b from-black/10 via-black/60 to-black pointer-events-none"
        />

        <div className="relative z-10 w-full space-y-8 max-w-5xl">
          {/* Headline in Control TNT with exactly one word in Caveat italic: "source" */}
          <ScrollReveal delay={50} duration={850} distance={24}>
            <div className="space-y-4 max-w-4xl">
              <h1 className="font-heading text-4xl sm:text-6xl md:text-7xl lg:text-8xl font-medium tracking-tight text-white leading-[1.05]">
                Every spec, traced to its{" "}
                <span className="font-cursive italic font-normal text-white text-5xl sm:text-7xl md:text-8xl lg:text-9xl">
                  source
                </span>
                .
              </h1>
              <p className="font-sans text-base sm:text-xl text-zinc-300 max-w-3xl leading-relaxed">
                AI-assisted parametric intelligence that extracts semiconductor limits from
                datasheets, verifies test conditions, and proves every number.
              </p>
            </div>
          </ScrollReveal>

          {/* Large Search Field (Dark Greyish) with Search Button */}
          <ScrollReveal delay={250} duration={850} distance={24}>
            <form onSubmit={handleSubmit} className="w-full max-w-3xl">
              <div className="relative flex flex-col sm:flex-row items-stretch sm:items-center gap-2 rounded-[8px] border border-white/15 bg-[#121215] p-2 shadow-none">
                <div className="flex items-center flex-1 px-3 py-1">
                  <Search className="size-5 text-zinc-400 mr-3 shrink-0" />
                  <input
                    id="search-input"
                    aria-label="Query"
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask in natural language (e.g. 100V N-channel MOSFET, Rds(on) < 5mΩ)..."
                    className="w-full bg-transparent font-sans text-base text-white placeholder:text-zinc-500 outline-none"
                  />
                </div>
                <button
                  type="submit"
                  className="rounded-[8px] bg-white px-6 py-3 font-medium text-sm text-black hover:bg-zinc-200 transition-none whitespace-nowrap cursor-pointer"
                >
                  Search
                </button>
              </div>
            </form>
          </ScrollReveal>

          {/* Example queries as pill toggles */}
          <ScrollReveal delay={400} duration={850} distance={24}>
            <div className="space-y-2">
              <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-400">
                Suggested queries:
              </div>
              <div className="flex flex-wrap gap-2">
                {SAMPLE_QUERIES.map((sample) => (
                  <button
                    key={sample}
                    type="button"
                    onClick={() => handleSampleClick(sample)}
                    className="rounded-full border border-white/20 bg-white/[0.04] px-4 py-1.5 text-xs text-white hover:bg-white/10 active:bg-white/15 focus-visible:outline-2 focus-visible:outline-white transition select-none text-left cursor-pointer"
                  >
                    {sample}
                  </button>
                ))}
              </div>
            </div>
          </ScrollReveal>
        </div>

        {/* Themed Scroll Indicator */}
        <div
          aria-label="Scroll to explore"
          role="button"
          tabIndex={0}
          onClick={() => {
            document.getElementById("features")?.scrollIntoView({ behavior: "smooth" });
          }}
          className={cn(
            "absolute bottom-8 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 cursor-pointer transition-all duration-300 select-none group",
            scrolled
              ? "opacity-0 pointer-events-none translate-y-2"
              : "opacity-70 hover:opacity-100",
          )}
        >
          <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400 group-hover:text-white transition-colors">
            Scroll to explore
          </span>
          <div className="w-5 h-8 rounded-full border border-white/20 group-hover:border-white/40 flex justify-center pt-1.5 transition-colors">
            <div className="w-1 h-2 bg-white/70 rounded-full animate-bounce" />
          </div>
        </div>
      </section>

      {/* Built for hardware engineers: how it works */}
      <section
        id="how-it-works"
        className="py-24 px-4 sm:px-8 lg:px-12 border-b border-white/10 w-full scroll-mt-20"
      >
        <ScrollReveal delay={50} duration={750} distance={28}>
          <div className="space-y-3 max-w-3xl">
            <h2 className="font-heading text-3xl sm:text-4xl font-medium text-white tracking-tight">
              How PartPilot works
            </h2>
            <p className="text-zinc-400 text-base sm:text-lg leading-relaxed">
              From a natural-language query to a verified, traceable specification — in three steps.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 lg:gap-16 mt-16">
          {HOW_IT_WORKS.map((step, i) => (
            <ScrollReveal delay={120 + i * 140} duration={750} distance={32} key={step.title}>
              <div className="group space-y-3 transition-transform duration-300 hover:-translate-y-1">
                <div className="font-mono text-sm font-semibold text-zinc-500 group-hover:text-signal-blue transition-colors">
                  0{i + 1}
                </div>
                <h3 className="font-heading text-lg font-medium text-white leading-snug">
                  {step.title}
                </h3>
                <p className="text-sm text-zinc-400 leading-relaxed font-sans">{step.desc}</p>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* Capabilities grid */}
      <section
        id="features"
        className="py-24 px-4 sm:px-8 lg:px-12 border-b border-white/10 w-full scroll-mt-20"
      >
        <ScrollReveal delay={50} duration={750} distance={28}>
          <div className="space-y-3 max-w-3xl">
            <h2 className="font-heading text-3xl sm:text-4xl font-medium text-white tracking-tight">
              Built for hardware engineers
            </h2>
            <p className="text-zinc-400 text-base sm:text-lg leading-relaxed">
              Reliable specifications backed by original engineering documentation.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 lg:gap-16 mt-16">
          {CAPABILITIES.map((cap, i) => (
            <ScrollReveal delay={120 + i * 110} duration={750} distance={32} key={cap.title}>
              <FeatureCard {...cap} />
            </ScrollReveal>
          ))}
        </div>
      </section>

      {/* Compressed Display Statement in Anton 900 near footer */}
      <section className="py-24 px-4 sm:px-8 lg:px-12 border-b border-white/10 overflow-hidden text-center select-none w-full">
        <div className="w-full">
          <ScrollReveal delay={80} duration={950} distance={40} scale={0.96}>
            <div className="font-compressed text-[clamp(48px,11vw,160px)] font-black uppercase text-white leading-[0.85] tracking-tight">
              TRACE EVERY NUMBER.
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 sm:px-8 lg:px-12 text-xs text-zinc-400 font-sans w-full">
        <ScrollReveal delay={60} duration={700} distance={20}>
          <div className="w-full flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
            <div className="space-y-2 max-w-xl">
              <div className="flex items-center gap-2">
                <PartPilotLogo size={18} />
                <span className="text-white font-medium">PartPilot Component Intelligence</span>
              </div>
              <p className="text-zinc-400">
                Data aggregated from authorized distributor APIs (DigiKey, Mouser, element14 India,
                Robu.in, Evelta) and official manufacturer datasheets.
              </p>
              <p className="text-zinc-500 text-[11px]">
                Academic research project for Web Data Mining. Respects source distributor terms,
                rate limits, and manufacturer documentation copyrights.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white underline underline-offset-4 hover:text-zinc-300"
              >
                GitHub Repository
              </a>
            </div>
          </div>
        </ScrollReveal>
      </footer>
    </div>
  );
}
