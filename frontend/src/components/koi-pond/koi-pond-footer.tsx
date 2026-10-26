"use client";

import { ScrollReveal } from "@/components/ui/scroll-reveal";
import { PartPilotLogo } from "@/components/brand/logo";
import KoiPond from "./koi-pond";

/**
 * Landing-page footer with the moving koi / fishes background from the portfolio.
 * The canvas sits behind the footer content; content carries `data-koi-avoid` so the
 * fish steer around it. The footer is sized to give the koi room to swim.
 */
export function KoiPondFooter() {
    return (
        <footer className="relative w-full bg-black border-t border-white/10 overflow-hidden">
            {/* Moving fishes background — canvas fills the footer, behind the content. */}
            <KoiPond
                isLight={false}
                className="absolute inset-0 w-full h-full select-none"
                onStats={() => {
                    /* no-op: footer does not display stats */
                }}
            />

            {/* Footer content overlaid on the pond. Fish steer around these boxes. */}
            <div className="relative z-10 px-4 sm:px-8 lg:px-12 py-16 md:py-20 w-full">
                <ScrollReveal delay={60} duration={700} distance={20}>
                    <div className="w-full flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                        <div className="space-y-2 max-w-xl">
                            <div className="flex items-center gap-2" data-koi-avoid>
                                <PartPilotLogo size={18} />
                                <span className="text-white font-medium">PartPilot Component Intelligence</span>
                            </div>
                            <p className="text-zinc-400" data-koi-avoid>
                                Data aggregated from authorized distributor APIs (DigiKey, Mouser, element14 India,
                                Robu.in, Evelta) and official manufacturer datasheets.
                            </p>
                            <p className="text-zinc-500 text-[11px]" data-koi-avoid>
                                Academic research project for Web Data Mining. Respects source distributor terms,
                                rate limits, and manufacturer documentation copyrights.
                            </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-4 text-xs font-mono" data-koi-avoid>
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
            </div>
        </footer>
    );
}
