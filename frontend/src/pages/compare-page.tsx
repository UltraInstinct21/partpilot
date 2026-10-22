import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LifecycleBadge } from "@/components/lifecycle-badge";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/loading-skeleton";
import { useParts, usePartsList } from "@/api/hooks";
import type { PartRecord } from "@/api/hooks";
import { bestValue } from "@/lib/compare";
import { formatNumber, humanizeParam } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_PARTS = 4;

/** The compare page: two to four parts side by side. */
export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = useMemo(
    () =>
      (searchParams.get("parts") ?? "")
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean),
    [searchParams],
  );

  const partsQuery = useParts({ limit: 50 });
  const partQueries = usePartsList(selected);

  const records = partQueries
    .map((query) => query.data)
    .filter((part): part is PartRecord => Boolean(part));

  const parameterNames = useMemo(() => {
    const names: string[] = [];
    for (const part of records) {
      for (const value of part.parameters ?? []) {
        if (!names.includes(value.name)) names.push(value.name);
      }
    }
    return names;
  }, [records]);

  const togglePart = (partId: string) => {
    const next = selected.includes(partId)
      ? selected.filter((id) => id !== partId)
      : [...selected, partId].slice(0, MAX_PARTS);
    setSearchParams(next.length > 0 ? { parts: next.join(",") } : {});
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Compare</h1>
        <p className="text-sm text-muted-foreground">
          Pick two to four parts and compare their parameters side by side. The best value of a
          "lower is better" parameter is highlighted.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Parts ({selected.length}/{MAX_PARTS})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {partsQuery.isPending && <TableSkeleton rows={4} cols={2} />}
          {partsQuery.isError && (
            <ErrorState
              title="The parts could not be loaded"
              error={partsQuery.error}
              onRetry={() => void partsQuery.refetch()}
            />
          )}
          <div className="grid max-h-64 grid-cols-1 gap-1 overflow-y-auto md:grid-cols-2 lg:grid-cols-3">
            {(partsQuery.data?.results ?? []).map((part) => (
              <label
                key={part.part_id}
                className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-muted/60"
              >
                <Checkbox
                  checked={selected.includes(part.part_id)}
                  onCheckedChange={() => togglePart(part.part_id)}
                  aria-label={`Select ${part.mpn}`}
                />
                <span className="font-mono">{part.mpn}</span>
                <span className="truncate text-xs text-muted-foreground">{part.manufacturer}</span>
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      {selected.length < 2 ? (
        <p className="text-sm text-muted-foreground">
          Select at least two parts to see the comparison.
        </p>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Side by side</CardTitle>
          </CardHeader>
          <CardContent>
            {partQueries.some((query) => query.isPending) && <TableSkeleton rows={6} cols={3} />}
            {partQueries.some((query) => query.isError) && (
              <ErrorState
                title="A part could not be loaded"
                error={partQueries.find((query) => query.isError)?.error}
              />
            )}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-40">Parameter</TableHead>
                    {records.map((part) => (
                      <TableHead key={part.part_id} className="min-w-48">
                        <div className="flex flex-col gap-1">
                          <Link
                            to={`/parts/${part.part_id}`}
                            className="font-mono underline underline-offset-4"
                          >
                            {part.mpn}
                          </Link>
                          <span className="text-xs font-normal text-muted-foreground">
                            {part.manufacturer}
                          </span>
                          <LifecycleBadge status={part.lifecycle_status} />
                        </div>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {parameterNames.map((name) => {
                    const values = records.map((part) => {
                      const found = (part.parameters ?? []).find((value) => value.name === name);
                      return found?.value ?? null;
                    });
                    const best = bestValue(name, values);
                    return (
                      <TableRow key={name}>
                        <TableCell className="font-medium">{humanizeParam(name)}</TableCell>
                        {records.map((part, index) => {
                          const found = (part.parameters ?? []).find(
                            (value) => value.name === name,
                          );
                          const value = values[index];
                          const isBest = best !== null && value !== null && value === best;
                          return (
                            <TableCell
                              key={part.part_id}
                              className={cn(
                                "font-mono tabular-nums",
                                isBest && "bg-green-100/60 font-semibold dark:bg-green-900/30",
                              )}
                            >
                              {value === null || value === undefined
                                ? "-"
                                : `${formatNumber(value)}${found?.unit ? ` ${found.unit}` : ""}`}
                              {isBest && (
                                <Badge variant="outline" className="ml-2">
                                  best
                                </Badge>
                              )}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
