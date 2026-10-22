import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts";
import { ErrorState } from "@/components/error-state";
import { PageSkeleton } from "@/components/loading-skeleton";
import { useStats } from "@/api/hooks";

const familyChartConfig = {
  parts: { label: "Parts", color: "var(--chart-1)" },
} satisfies ChartConfig;

const statusChartConfig = {
  accepted: { label: "Accepted", color: "var(--chart-2)" },
  review: { label: "Review", color: "var(--chart-3)" },
  rejected: { label: "Rejected", color: "var(--chart-4)" },
} satisfies ChartConfig;

const tokenChartConfig = {
  tokensIn: { label: "Tokens in", color: "var(--chart-1)" },
  tokensOut: { label: "Tokens out", color: "var(--chart-2)" },
} satisfies ChartConfig;

function toEntries(record: Record<string, number> | undefined): Array<{
  name: string;
  value: number;
}> {
  return Object.entries(record ?? {}).map(([name, value]) => ({ name, value }));
}

/** The dashboard: extraction accuracy, cost and coverage. */
export function DashboardPage() {
  const statsQuery = useStats();
  const stats = statsQuery.data;

  if (statsQuery.isPending) {
    return <PageSkeleton />;
  }

  if (statsQuery.isError || !stats) {
    return (
      <ErrorState
        title="The statistics could not be loaded"
        error={statsQuery.error}
        onRetry={() => void statsQuery.refetch()}
      />
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
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Coverage, accuracy and the cost of the extraction.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Parts</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">{stats.parts_total ?? 0}</p>
            <p className="text-xs text-muted-foreground">
              {stats.parameters_total ?? 0} parameters · {stats.sources_total ?? 0} sources
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Coverage</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">{stats.coverage_pct ?? 0}%</p>
            <Progress value={stats.coverage_pct ?? 0} className="mt-2" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mean confidence
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">
              {Math.round((stats.mean_confidence ?? 0) * 100)}%
            </p>
            <p className="text-xs text-muted-foreground">
              {stats.review_pending ?? 0} values wait for a review
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">LLM cost</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold tabular-nums">
              ${(stats.llm_cost_total ?? 0).toFixed(2)}
            </p>
            <p className="text-xs text-muted-foreground">
              {stats.llm_calls_total ?? 0} calls · ${(stats.avg_cost_per_datasheet ?? 0).toFixed(2)}{" "}
              per datasheet
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Parts per family</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={familyChartConfig} className="min-h-[240px] w-full">
              <BarChart data={familyData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="name" tickLine={false} tickMargin={10} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="value" fill="var(--color-parts)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Values by status</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={statusChartConfig} className="min-h-[240px] w-full">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent nameKey="name" />} />
                <ChartLegend content={<ChartLegendContent nameKey="name" />} />
                <Pie
                  data={statusData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={50}
                  outerRadius={85}
                >
                  {statusData.map((entry) => (
                    <Cell key={entry.name} fill={`var(--color-${entry.name})`} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={tokenChartConfig} className="min-h-[240px] w-full">
              <BarChart data={tokenData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="name" tickLine={false} tickMargin={10} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="tokensIn" fill="var(--color-tokensIn)" radius={4} />
                <Bar dataKey="tokensOut" fill="var(--color-tokensOut)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Accuracy per family</CardTitle>
          </CardHeader>
          <CardContent>
            {accuracyData.length === 0 ? (
              <p className="text-sm text-muted-foreground">No accuracy was measured yet.</p>
            ) : (
              <ul className="space-y-3">
                {accuracyData.map((entry) => (
                  <li key={entry.name} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="capitalize">{entry.name}</span>
                      <span className="tabular-nums text-muted-foreground">
                        {Math.round(entry.value * 100)}%
                      </span>
                    </div>
                    <Progress value={entry.value * 100} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
