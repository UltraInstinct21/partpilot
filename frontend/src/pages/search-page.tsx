import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createColumnHelper, flexRender, type SortingState, useTable } from "@tanstack/react-table";
import { Download, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FilterChips } from "@/components/filter-chips";
import { LifecycleBadge } from "@/components/lifecycle-badge";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/loading-skeleton";
import { useSearch } from "@/api/hooks";
import type { PartSummary, SearchFilter } from "@/api/hooks";
import { sortingFeatures } from "@/lib/table";
import { downloadTextFile, humanizeParam, toCsv } from "@/lib/format";

type SearchRequestState = { query: string; filter: SearchFilter | null };

function collectKeyParameters(results: PartSummary[]): string[] {
  const keys: string[] = [];
  for (const part of results) {
    for (const key of Object.keys(part.key_parameters ?? {})) {
      if (!keys.includes(key)) keys.push(key);
    }
  }
  return keys.slice(0, 4);
}

const helper = createColumnHelper<typeof sortingFeatures, PartSummary>();

/** The search page (FR-11). */
export function SearchPage() {
  const [query, setQuery] = useState("");
  const [request, setRequest] = useState<SearchRequestState | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);

  const searchQuery = useSearch(request);
  const results = useMemo(() => searchQuery.data?.results ?? [], [searchQuery.data]);
  const activeFilter = searchQuery.data?.filter;

  const columns = useMemo(() => {
    const keyNames = collectKeyParameters(results);
    return helper.columns([
      helper.accessor("mpn", {
        header: "MPN",
        cell: (info) => (
          <Link
            to={`/parts/${info.row.original.part_id}`}
            className="font-medium underline underline-offset-4"
          >
            {info.getValue()}
          </Link>
        ),
      }),
      helper.accessor("manufacturer", { header: "Manufacturer" }),
      helper.accessor("family", { header: "Family" }),
      helper.accessor("package", {
        header: "Package",
        cell: (info) => info.getValue() ?? "-",
      }),
      helper.accessor("lifecycle_status", {
        header: "Lifecycle",
        cell: (info) => <LifecycleBadge status={info.getValue()} />,
      }),
      ...keyNames.map((key) =>
        helper.accessor((row) => row.key_parameters?.[key] ?? null, {
          id: key,
          header: humanizeParam(key),
          cell: (info) => (info.getValue() === null ? "-" : String(info.getValue())),
        }),
      ),
    ]);
  }, [results]);

  const table = useTable({
    features: sortingFeatures,
    columns,
    data: results,
    state: { sorting },
    onSortingChange: setSorting,
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    // A new query goes to the language model; the filter is not sent.
    setRequest({ query: trimmed, filter: null });
  };

  const handleFilterChange = (filter: SearchFilter) => {
    setRequest((previous) =>
      previous ? { ...previous, filter } : { query: query.trim(), filter },
    );
  };

  const handleExport = () => {
    const keyNames = collectKeyParameters(results);
    const header = [
      "part_id",
      "mpn",
      "manufacturer",
      "family",
      "package",
      "lifecycle_status",
      ...keyNames,
    ];
    const rows = results.map((part) => [
      part.part_id,
      part.mpn,
      part.manufacturer,
      part.family,
      part.package ?? "",
      part.lifecycle_status ?? "",
      ...keyNames.map((key) => part.key_parameters?.[key] ?? ""),
    ]);
    downloadTextFile("partpilot-search-results.csv", toCsv(header, rows));
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="text-sm text-muted-foreground">
          Describe the part you need in plain language. The filter that was built from your sentence
          can be edited before the result is used.
        </p>
      </header>

      <Card>
        <CardContent className="space-y-4">
          <form onSubmit={handleSubmit} className="flex flex-col gap-2">
            <Label htmlFor="search-query">Query</Label>
            <div className="flex gap-2">
              <Input
                id="search-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="e.g. 100V N-channel MOSFET with rds(on) below 10 mOhm"
                autoComplete="off"
              />
              <Button type="submit" disabled={!query.trim() || searchQuery.isFetching}>
                <Search className="size-4" />
                Search
              </Button>
            </div>
          </form>

          {activeFilter && <FilterChips filter={activeFilter} onChange={handleFilterChange} />}
        </CardContent>
      </Card>

      {searchQuery.isError && (
        <ErrorState
          title="The search failed"
          error={searchQuery.error}
          onRetry={() => void searchQuery.refetch()}
        />
      )}

      {searchQuery.isPending && request && <TableSkeleton rows={6} cols={6} />}

      {searchQuery.data && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">
              {searchQuery.data.total} part{searchQuery.data.total === 1 ? "" : "s"} found
              {searchQuery.data.took_ms !== undefined && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  in {searchQuery.data.took_ms} ms
                </span>
              )}
            </CardTitle>
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="size-4" />
              Export CSV
            </Button>
          </CardHeader>
          <CardContent>
            {results.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No part matches this filter.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    {table.getHeaderGroups().map((group) => (
                      <TableRow key={group.id}>
                        {group.headers.map((header) => (
                          <TableHead key={header.id}>
                            {header.column.getCanSort() ? (
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 font-medium hover:text-foreground"
                                onClick={() => header.column.toggleSorting()}
                              >
                                {flexRender(header.column.columnDef.header, header.getContext())}
                                <span aria-hidden className="text-[10px]">
                                  {header.column.getIsSorted() === "asc"
                                    ? "▲"
                                    : header.column.getIsSorted() === "desc"
                                      ? "▼"
                                      : "↕"}
                                </span>
                              </button>
                            ) : (
                              flexRender(header.column.columnDef.header, header.getContext())
                            )}
                          </TableHead>
                        ))}
                      </TableRow>
                    ))}
                  </TableHeader>
                  <TableBody>
                    {table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id}>
                        {row.getAllCells().map((cell) => (
                          <TableCell key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {searchQuery.data.filter_explanation && (
              <p className="mt-3 text-xs text-muted-foreground">
                {searchQuery.data.filter_explanation}
                {searchQuery.data.llm_used === false && " (served from the cache)"}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
