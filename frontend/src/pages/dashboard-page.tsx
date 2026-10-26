import { useState } from "react";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Bar, BarChart, CartesianGrid, Pie, PieChart, Cell, XAxis, YAxis, ResponsiveContainer } from "recharts";
import { ErrorState } from "@/components/error-state";
import { PageSkeleton } from "@/components/loading-skeleton";
import { useStats } from "@/api/hooks";
import { BarChart3, Table as TableIcon } from "lucide-react";

// Strict monochrome styling per DESIGN.md:
const familyChartConfig = {
  parts: { label: "Parts", color: "#ffffff" },
} satisfies ChartConfig;

const statusChartConfig = {
  accepted: { label: "Accepted", color: "#ffffff" },
  review: { label: "Review", color: "#a1a1aa" },
  rejected: { label: "Rejected", color: "#52525b" },
} satisfies ChartConfig;

const tokenChartConfig = {
  tokensIn: { label: "Tokens in", color: "#ffffff" },
  tokensOut: { label: "Tokens out", color: "#a1a1aa" },
} satisfies ChartConfig;

function toEntries(record: Record<string, number> | undefined): Array<{
  name: string;
  value: number;
}> {
  return Object.entries(record ?? {}).map(([name, value]) => ({ name, value }));
}

/**
 * The platform intelligence dashboard: extraction accuracy, cost, and telemetry.
 * Styled inside sleek dark grey cards matching the rest of the site.
 */
export function DashboardPage() {
  const statsQuery = useStats();
  const stats = statsQuery.data;

  const [showFamilyTable, setShowFamilyTable] = useState(false);
  const [showStatusTable, setShowStatusTable] = useState(false);
  const [showTokenTable, setShowTokenTable] = useState(false);
  const [showAccuracyTable, setShowAccuracyTable] = useState(false);

  if (statsQuery.isPending) {
    return (
      <PageSkeleton
        title="Loading telemetry & pipeline statistics…"
        description="Aggregating database counts, token expenditures, and extraction accuracy metrics."
      />
    );
  }

  if (statsQuery.isError || !stats) {
    return (
      <div className="w-full">
        <ErrorState
          title="The statistics could not be loaded"
          error={statsQuery.error}
          onRetry={() => void statsQuery.refetch()}
        />
      </div>
    );
  }

  const familyData = toEntries(stats.parts_by_family);
  const statusData = toEntries(stats.values_by_status);
  const tokenData = [
    { name: "Tokens in", tokensIn: stats.llm_tokens_in ?? 0, tokensOut: 0 },
    { name: "Tokens out", tokensIn: 0, tokensOut: stats.llm_tokens_out ?? 0 },
  ];
  const accuracyData = toEntries(stats.accuracy);

  return (
    <div className="space-y-8 w-full">
      {/* Header */}
      <header className="space-y-2 border-b border-white/10 pb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="size-5 text-white" />
          <h1 className="font-heading text-2xl font-semibold tracking-tight text-white">
            Platform Intelligence & Analytics
          </h1>
        </div>
        <p className="text-xs text-zinc-400 font-sans">
          Telemetry on extraction coverage, validation precision, LLM token efficiency, and
          distributor ingestion health.
        </p>
      </header>

      {/* KPI Metric Strip - Clean hairline separation */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-white/10 border-y border-white/10 py-6 w-full">
        <div className="sm:px-6 py-2 space-y-1 first:sm:pl-0">
          <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">Parts</div>
          <div className="text-3xl font-mono font-semibold tracking-tight text-white tabular-nums">
            {stats.parts_total ?? 0}
          </div>
          <div className="text-[11px] font-mono text-zinc-400">
            {stats.parameters_total ?? 0} parameters, {stats.sources_total ?? 0} datasheets
          </div>
        </div>

        <div className="sm:px-6 py-2 space-y-1">
          <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">Coverage</div>
          <div className="text-3xl font-mono font-semibold tracking-tight text-white tabular-nums">
            {stats.coverage_pct ?? 0}%
          </div>
          <div className="mt-2 h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-white"
              style={{ width: `${Math.min(100, Math.max(0, stats.coverage_pct ?? 0))}%` }}
            />
          </div>
        </div>

        <div className="sm:px-6 py-2 space-y-1">
          <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">
            Mean confidence
          </div>
          <div className="text-3xl font-mono font-semibold tracking-tight text-white tabular-nums">
            {Math.round((stats.mean_confidence ?? 0) * 100)}%
          </div>
          <div className="text-[11px] font-mono text-zinc-400">
            {stats.review_pending ?? 0} values awaiting review
          </div>
        </div>

        <div className="sm:px-6 py-2 space-y-1 last:sm:pr-0">
          <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">LLM cost</div>
          <div className="text-3xl font-mono font-semibold tracking-tight text-white tabular-nums">
            ${(stats.llm_cost_total ?? 0).toFixed(2)}
          </div>
          <div className="text-[11px] font-mono text-zinc-400">
            {stats.llm_calls_total ?? 0} model calls, $
            {(stats.avg_cost_per_datasheet ?? 0).toFixed(2)} per datasheet
          </div>
        </div>
      </div>

      {/* Visual Charts (Clean open panels, no heavy grey card boxes) */}
      <div className="grid gap-12 lg:grid-cols-2 w-full pt-4">
        {/* Parts per Family */}
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <h2 className="font-heading text-sm font-semibold text-white">Parts per family</h2>
            <button
              type="button"
              onClick={() => setShowFamilyTable(!showFamilyTable)}
              className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-white underline"
            >
              <TableIcon className="size-3" />
              <span>{showFamilyTable ? "View chart" : "View as table"}</span>
            </button>
          </div>

          {showFamilyTable ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/10 text-zinc-400">
                    <th className="py-2">Family</th>
                    <th className="py-2 text-right">Parts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {familyData.map((d) => (
                    <tr key={d.name}>
                      <td className="py-1.5 uppercase text-zinc-200">{d.name}</td>
                      <td className="py-1.5 text-right font-bold text-white">{d.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ChartContainer config={familyChartConfig} className="min-h-[220px] w-full">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={familyData}>
                  <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.08)" />
                  <XAxis
                    dataKey="name"
                    tickLine={false}
                    tickMargin={8}
                    axisLine={false}
                    stroke="#888"
                    fontSize={11}
                  />
                  <YAxis tickLine={false} axisLine={false} stroke="#888" fontSize={11} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="value" fill="#ffffff" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </ChartContainer>
          )}
        </div>

        {/* Values by Status */}
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <h2 className="font-heading text-sm font-semibold text-white">Values by status</h2>
            <button
              type="button"
              onClick={() => setShowStatusTable(!showStatusTable)}
              className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-white underline"
            >
              <TableIcon className="size-3" />
              <span>{showStatusTable ? "View chart" : "View as table"}</span>
            </button>
          </div>

          {showStatusTable ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/10 text-zinc-400">
                    <th className="py-2">Status</th>
                    <th className="py-2 text-right">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {statusData.map((d) => (
                    <tr key={d.name}>
                      <td className="py-1.5 uppercase text-zinc-200">{d.name}</td>
                      <td className="py-1.5 text-right font-bold text-white">{d.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ChartContainer config={statusChartConfig} className="min-h-[220px] w-full">
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <ChartTooltip content={<ChartTooltipContent nameKey="name" />} />
                  <ChartLegend content={<ChartLegendContent nameKey="name" />} />
                  <Pie
                    data={statusData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={45}
                    outerRadius={80}
                    stroke="#121215"
                    strokeWidth={2}
                  >
                    {statusData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={
                          entry.name === "accepted"
                            ? "#ffffff"
                            : entry.name === "review"
                              ? "#a1a1aa"
                              : "#52525b"
                        }
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </ChartContainer>
          )}
        </div>

        {/* LLM Tokens */}
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <h2 className="font-heading text-sm font-semibold text-white">LLM tokens</h2>
            <button
              type="button"
              onClick={() => setShowTokenTable(!showTokenTable)}
              className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-white underline"
            >
              <TableIcon className="size-3" />
              <span>{showTokenTable ? "View chart" : "View as table"}</span>
            </button>
          </div>

          {showTokenTable ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/10 text-zinc-400">
                    <th className="py-2">Direction</th>
                    <th className="py-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  <tr>
                    <td className="py-1.5 text-zinc-200">Tokens In</td>
                    <td className="py-1.5 text-right font-bold text-white">
                      {(stats.llm_tokens_in ?? 0).toLocaleString()}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1.5 text-zinc-200">Tokens Out</td>
                    <td className="py-1.5 text-right font-bold text-white">
                      {(stats.llm_tokens_out ?? 0).toLocaleString()}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <ChartContainer config={tokenChartConfig} className="min-h-[220px] w-full">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={tokenData}>
                  <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.08)" />
                  <XAxis
                    dataKey="name"
                    tickLine={false}
                    tickMargin={8}
                    axisLine={false}
                    stroke="#888"
                    fontSize={11}
                  />
                  <YAxis tickLine={false} axisLine={false} stroke="#888" fontSize={11} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="tokensIn" fill="#ffffff" radius={4} />
                  <Bar dataKey="tokensOut" fill="#a1a1aa" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </ChartContainer>
          )}
        </div>

        {/* Accuracy per Family */}
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <h2 className="font-heading text-sm font-semibold text-white">Accuracy per family</h2>
            <button
              type="button"
              onClick={() => setShowAccuracyTable(!showAccuracyTable)}
              className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-white underline"
            >
              <TableIcon className="size-3" />
              <span>{showAccuracyTable ? "View progress" : "View as table"}</span>
            </button>
          </div>

          {accuracyData.length === 0 ? (
            <p className="text-xs text-zinc-500 py-12 text-center font-mono">
              No accuracy was measured yet.
            </p>
          ) : showAccuracyTable ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/10 text-zinc-400">
                    <th className="py-2">Family</th>
                    <th className="py-2 text-right">Accuracy</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {accuracyData.map((d) => (
                    <tr key={d.name}>
                      <td className="py-1.5 uppercase text-zinc-200">{d.name}</td>
                      <td className="py-1.5 text-right font-bold text-white">
                        {Math.round(d.value * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ul className="space-y-4 pt-2">
              {accuracyData.map((entry) => (
                <li key={entry.name} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="capitalize font-medium text-white">{entry.name}</span>
                    <span className="tabular-nums font-mono text-zinc-300">
                      {Math.round(entry.value * 100)}%
                    </span>
                  </div>
                  <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-white"
                      style={{ width: `${Math.min(100, Math.max(0, entry.value * 100))}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
