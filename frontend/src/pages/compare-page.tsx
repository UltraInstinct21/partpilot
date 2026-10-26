import { useState, useMemo, Fragment } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Download,
  Trash2,
  AlertTriangle,
  X,
  Plus,
  Scale,
  Award,
} from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusTag } from "@/components/domain/status-tag";
import { SourceViewer } from "@/components/source-viewer";
import { TableSkeleton } from "@/components/loading-skeleton";
import { ErrorState } from "@/components/error-state";
import { usePart, useParts, type ParameterValue, type PartDetail } from "@/api/hooks";
import { useCompareSelection } from "@/lib/compare-store";
import {
  formatNumber,
  formatValue,
  humanizeParam,
  formatCondition,
  downloadTextFile,
  toCsv,
} from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_COMPARE_PARTS = 4;

// Standard metadata for compare rows
const PARAM_SYMBOLS: Record<string, { symbol?: string; group: string; label: string }> = {
  vds_max: { symbol: "V(BR)DSS", group: "Absolute Maximum Ratings", label: "Drain-Source Voltage" },
  id_continuous: { symbol: "ID", group: "Absolute Maximum Ratings", label: "Continuous Drain Current" },
  vgs_max: { symbol: "VGS", group: "Absolute Maximum Ratings", label: "Gate-Source Voltage" },
  power_dissipation_pd: { symbol: "PD", group: "Absolute Maximum Ratings", label: "Power Dissipation" },
  junction_temp_tj_max: { symbol: "Tj max", group: "Thermal Characteristics", label: "Max Junction Temp" },
  thermal_resistance_rthjc: { symbol: "RthJC", group: "Thermal Characteristics", label: "Thermal Res (Junction-Case)" },
  thermal_resistance_rthja: { symbol: "RthJA", group: "Thermal Characteristics", label: "Thermal Res (Junction-Amb)" },
  rds_on: { symbol: "RDS(on)", group: "Electrical Characteristics", label: "Static Drain-Source RDS(on)" },
  gate_threshold_vgs_th: { symbol: "VGS(th)", group: "Electrical Characteristics", label: "Gate Threshold Voltage" },
  total_gate_charge_qg: { symbol: "Qg", group: "Electrical Characteristics", label: "Total Gate Charge" },
  gate_source_charge_qgs: { symbol: "Qgs", group: "Electrical Characteristics", label: "Gate-Source Charge" },
  gate_drain_charge_qgd: { symbol: "Qgd", group: "Electrical Characteristics", label: "Gate-Drain Charge" },
  input_capacitance_ciss: { symbol: "Ciss", group: "Electrical Characteristics", label: "Input Capacitance" },
  output_capacitance_coss: { symbol: "Coss", group: "Electrical Characteristics", label: "Output Capacitance" },
  reverse_recovery_time_trr: { symbol: "trr", group: "Electrical Characteristics", label: "Reverse Recovery Time" },
  // Drivers
  supply_voltage_max: { symbol: "VCC(max)", group: "Absolute Maximum Ratings", label: "Max Supply Voltage" },
  peak_source_current: { symbol: "IO+", group: "Electrical Characteristics", label: "Peak Source Current" },
  peak_sink_current: { symbol: "IO-", group: "Electrical Characteristics", label: "Peak Sink Current" },
  propagation_delay: { symbol: "tpd", group: "Electrical Characteristics", label: "Propagation Delay" },
  channel_count: { symbol: "Channels", group: "Package & Configuration", label: "Channel Count" },
};

export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedParts, removePart, clearParts, togglePart } = useCompareSelection();

  // Part IDs from URL or compare store
  const urlIds = useMemo(() => {
    const raw = searchParams.get("ids");
    if (!raw) return [];
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }, [searchParams]);

  const selectedIds = useMemo(() => {
    if (urlIds.length > 0) return urlIds.slice(0, MAX_COMPARE_PARTS);
    return selectedParts.map((p) => p.id).slice(0, MAX_COMPARE_PARTS);
  }, [urlIds, selectedParts]);

  // Sync compare store parts to URL if no url param set
  const handleUpdateUrl = (ids: string[]) => {
    if (ids.length === 0) {
      setSearchParams({});
    } else {
      setSearchParams({ ids: ids.join(",") });
    }
  };

  // Queries for each part in comparison
  const partQuery1 = usePart(selectedIds[0] || "");
  const partQuery2 = usePart(selectedIds[1] || "");
  const partQuery3 = usePart(selectedIds[2] || "");
  const partQuery4 = usePart(selectedIds[3] || "");

  const partQueries = [partQuery1, partQuery2, partQuery3, partQuery4].slice(0, selectedIds.length);

  const isPending = partQueries.some((q) => q.isPending);
  const isError = partQueries.some((q) => q.isError);
  const records = useMemo(() => {
    return partQueries.map((q) => q.data).filter(Boolean) as PartDetail[];
  }, [partQueries]);

  // "Differences only" toggle
  const [differencesOnly, setDifferencesOnly] = useState(false);
  const [addPartOpen, setAddPartOpen] = useState(false);
  const [partPickerQuery, setPartPickerQuery] = useState("");
  const partsQuery = useParts({ q: partPickerQuery || undefined, limit: 20 });

  // Active parameter for Source Viewer Sheet
  const [activeParamSource, setActiveParamSource] = useState<{
    partId: string;
    param: ParameterValue;
  } | null>(null);

  const availableParts = partsQuery.data?.results ?? [];

  const handleTogglePart = (partId: string, mpn: string) => {
    let next: string[];
    if (selectedIds.includes(partId)) {
      next = selectedIds.filter((id) => id !== partId);
      removePart(partId);
    } else {
      if (selectedIds.length >= MAX_COMPARE_PARTS) return;
      next = [...selectedIds, partId];
      togglePart({ id: partId, mpn });
    }
    handleUpdateUrl(next);
  };

  const handleRemoveColumn = (partId: string) => {
    const next = selectedIds.filter((id) => id !== partId);
    removePart(partId);
    handleUpdateUrl(next);
  };

  const handleClearAll = () => {
    clearParts();
    handleUpdateUrl([]);
  };

  // Group parameters dynamically for side-by-side table across all families
  const groupedParameters = useMemo(() => {
    const groups: Record<string, string[]> = {
      "Absolute Maximum Ratings": [],
      "Electrical Characteristics": [],
      "Thermal Characteristics": [],
      "Package & Configuration": [],
    };

    const inferGroup = (name: string): string => {
      const lower = name.toLowerCase();
      if (PARAM_SYMBOLS[name]?.group) return PARAM_SYMBOLS[name].group;
      if (lower.includes("thermal") || lower.includes("temp") || lower.includes("rth") || lower.startsWith("tj")) {
        return "Thermal Characteristics";
      }
      if (lower.includes("max") || lower.includes("breakdown") || lower.includes("rating")) {
        return "Absolute Maximum Ratings";
      }
      if (lower.includes("package") || lower.includes("pin") || lower.includes("channel") || lower.includes("lead")) {
        return "Package & Configuration";
      }
      return "Electrical Characteristics";
    };

    const seen = new Set<string>();
    for (const record of records) {
      for (const p of record.parameters ?? []) {
        if (!seen.has(p.name)) {
          seen.add(p.name);
          const groupName = inferGroup(p.name);
          if (!groups[groupName]) {
            groups[groupName] = [];
          }
          groups[groupName].push(p.name);
        }
      }
    }

    return groups;
  }, [records]);

  // Determine "best in row" numeric index
  const getBestInRow = (paramName: string, items: (ParameterValue | undefined)[]) => {
    const valid = items
      .map((item, idx) => ({ idx, val: item?.value }))
      .filter((entry): entry is { idx: number; val: number } => entry.val !== null && entry.val !== undefined);

    if (valid.length < 2) return null;

    // Lower is better: rds_on, qg, propagation_delay, thermal_resistance
    const lowerIsBetter = [
      "rds_on",
      "total_gate_charge_qg",
      "gate_source_charge_qgs",
      "gate_drain_charge_qgd",
      "propagation_delay",
      "thermal_resistance_rthjc",
      "thermal_resistance_rthja",
      "reverse_recovery_time_trr",
    ].includes(paramName);

    if (lowerIsBetter) {
      const min = Math.min(...valid.map((e) => e.val));
      return min;
    } else {
      const max = Math.max(...valid.map((e) => e.val));
      return max;
    }
  };

  // Detect condition discrepancies across row
  const checkDifferentConditions = (items: (ParameterValue | undefined)[]) => {
    const defined = items.filter(Boolean) as ParameterValue[];
    if (defined.length < 2) return false;
    const firstCond = JSON.stringify(defined[0].condition || {});
    return defined.some((item) => JSON.stringify(item.condition || {}) !== firstCond);
  };

  // Export comparison as CSV
  const handleExportCsv = () => {
    if (records.length === 0) return;
    const rows: Record<string, unknown>[] = [];

    // General meta
    const mfrRow: Record<string, unknown> = { Parameter: "Manufacturer" };
    const pkgRow: Record<string, unknown> = { Parameter: "Package" };
    const statusRow: Record<string, unknown> = { Parameter: "Status" };

    records.forEach((r) => {
      mfrRow[r.mpn] = r.manufacturer;
      pkgRow[r.mpn] = r.package ?? "-";
      statusRow[r.mpn] = r.lifecycle_status ?? "unknown";
    });

    rows.push(mfrRow, pkgRow, statusRow);

    // Param rows
    Object.values(groupedParameters).flat().forEach((paramName) => {
      const row: Record<string, unknown> = {
        Parameter: humanizeParam(paramName),
      };
      records.forEach((r) => {
        const found = (r.parameters ?? []).find((p: ParameterValue) => p.name === paramName);
        row[r.mpn] = found ? formatValue(found.value, found.unit) : "-";
      });
      rows.push(row);
    });

    const csv = toCsv(rows);
    downloadTextFile(`partpilot-compare-${Date.now()}.csv`, csv, "text/csv;charset=utf-8;");
  };

  return (
    <div className="space-y-6 w-full">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Scale className="size-5 text-white" />
            <h1 className="font-heading text-2xl font-semibold tracking-tight text-white">
              Component Comparison
            </h1>
          </div>
          <p className="text-xs text-zinc-400 font-sans mt-1">
            Side-by-side engineering specifications, test condition discrepancy checks, and best-in-row analysis.
          </p>
        </div>

        {records.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClearAll}
              className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 transition-none"
            >
              <Trash2 className="size-3.5" />
              <span>Clear comparison</span>
            </button>
            <button
              type="button"
              onClick={handleExportCsv}
              className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 transition-none"
            >
              <Download className="size-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        )}
      </div>

      {selectedIds.length >= 2 && isPending && (
        <TableSkeleton
          rows={8}
          cols={selectedIds.length + 1}
          title="Aligning electrical parameters for comparison…"
          description="Correlating electrical ratings, switching characteristics, and package pinouts."
        />
      )}
      {isError && <ErrorState title="Could not load one or more comparison parts." />}

      {/* Part Picker if fewer than 2 parts selected */}
      {records.length < 2 && (
        <div className="space-y-4 w-full">
          <div className="text-xs font-mono uppercase font-bold text-zinc-400">
            Select parts to compare (choose at least 2):
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {availableParts.map((p) => {
              const isChecked = selectedIds.includes(p.part_id);
              return (
                <div
                  key={p.part_id}
                  onClick={() => handleTogglePart(p.part_id, p.mpn)}
                  className={cn(
                    "flex items-center gap-2.5 rounded-[8px] border p-3.5 cursor-pointer text-xs select-none transition-colors",
                    isChecked
                      ? "border-white bg-white/15 font-medium text-white"
                      : "border-white/10 bg-white/[0.03] text-zinc-300 hover:border-white/25 hover:bg-white/[0.06]",
                  )}
                >
                  <Checkbox
                    checked={isChecked}
                    onCheckedChange={() => {}}
                  />
                  <div className="flex-1 truncate">
                    <div className="font-mono font-medium text-white truncate">{p.mpn}</div>
                    <div className="text-[11px] text-zinc-400 truncate">{p.manufacturer}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Compare Table Area (Unboxed, clean separation) */}
      {records.length >= 2 && (
        <div className="space-y-4 w-full">
          {/* Controls: "Differences only" toggle & Add Part button */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
            <div className="flex items-center gap-4 text-xs">
              <span className="font-mono font-bold text-white">Side by side</span>
              <label className="flex items-center gap-2 cursor-pointer select-none text-zinc-300">
                <input
                  type="checkbox"
                  checked={differencesOnly}
                  onChange={(e) => setDifferencesOnly(e.target.checked)}
                  className="size-3.5 rounded-[2px] border-white/20 bg-white/5 text-white"
                />
                <span className="font-medium text-white">Differences only</span>
              </label>
            </div>

            {selectedIds.length < MAX_COMPARE_PARTS && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setAddPartOpen(!addPartOpen)}
                  className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10"
                >
                  <Plus className="size-3.5" />
                  <span>Add component ({selectedIds.length}/4)</span>
                </button>

                {addPartOpen && (
                  <div className="absolute right-0 mt-1 w-64 rounded-[8px] border border-white/15 bg-[#18181c] p-2 text-xs shadow-none z-50 max-h-60 overflow-y-auto space-y-1">
                    <input
                      value={partPickerQuery}
                      onChange={(event) => setPartPickerQuery(event.target.value)}
                      placeholder="Search indexed parts..."
                      className="w-full rounded border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white outline-none placeholder:text-zinc-500"
                      autoFocus
                    />
                    <div className="font-mono uppercase text-[10px] font-bold text-zinc-400 px-2 py-1">
                      Choose Part to Add
                    </div>
                    {availableParts
                      .filter((p) => !selectedIds.includes(p.part_id))
                      .map((p) => (
                        <button
                          key={p.part_id}
                          type="button"
                          onClick={() => {
                            handleTogglePart(p.part_id, p.mpn);
                            setAddPartOpen(false);
                          }}
                          className="w-full text-left px-2 py-1.5 rounded-[4px] hover:bg-white/10 text-zinc-300 hover:text-white flex items-center justify-between"
                        >
                          <span className="font-mono font-medium">{p.mpn}</span>
                          <span className="text-[11px] text-zinc-400">{p.manufacturer}</span>
                        </button>
                      ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Side by Side Comparison Table */}
          <div className="overflow-x-auto border-b border-white/10">
            <table className="w-full text-left text-xs font-sans table-fixed">
              {/* Sticky Header with Parts */}
              <thead className="bg-black border-b border-white/15 sticky top-0 z-10 select-none">
                <tr>
                  <th
                    scope="col"
                    role="columnheader"
                    className="w-56 px-4 py-3 font-mono text-[11px] uppercase tracking-wider text-zinc-400 bg-black sticky left-0 z-20 border-r border-white/10"
                  >
                    Parameter
                  </th>
                  {records.map((part) => (
                    <th
                      key={part.part_id}
                      scope="col"
                      role="columnheader"
                      className="px-4 py-3 font-sans align-top border-r border-white/10 last:border-r-0"
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-start justify-between gap-1">
                          <Link
                            to={`/parts/${part.part_id}`}
                            className="font-heading text-sm font-semibold text-white hover:text-zinc-200 underline underline-offset-2"
                          >
                            {part.mpn}
                          </Link>
                          <button
                            type="button"
                            onClick={() => handleRemoveColumn(part.part_id)}
                            aria-label={`Remove ${part.mpn} from comparison`}
                            className="text-zinc-400 hover:text-white p-0.5 rounded-[2px]"
                          >
                            <X className="size-3.5" />
                          </button>
                        </div>
                        <div className="text-[11px] text-zinc-400">{part.manufacturer}</div>
                        <StatusTag status={part.lifecycle_status ?? "unknown"} type="lifecycle" />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody className="divide-y divide-white/5">
                {/* General metadata rows */}
                <tr className="hover:bg-white/[0.04]">
                  <td className="px-4 py-2.5 font-mono text-zinc-400 sticky left-0 bg-black border-r border-white/10">
                    Package
                  </td>
                  {records.map((p) => (
                    <td key={p.part_id} className="px-4 py-2.5 font-mono text-zinc-200 border-r border-white/10 last:border-r-0">
                      {p.package ?? "-"}
                    </td>
                  ))}
                </tr>

                {/* Grouped parameter categories & rows */}
                {Object.entries(groupedParameters).map(([groupTitle, paramNames]) => {
                  const filteredParamNames = paramNames.filter((paramName) => {
                    const items = records.map((part) =>
                      (part.parameters ?? []).find((p: ParameterValue) => p.name === paramName),
                    );
                    const values = items.map((item) => item?.value);
                    const allEqual = values.every((v) => v === values[0]);
                    return !(differencesOnly && allEqual && values[0] !== undefined);
                  });

                  if (filteredParamNames.length === 0) return null;

                  return (
                    <Fragment key={`group-${groupTitle}`}>
                      <tr className="bg-white/[0.04] font-mono text-[11px] uppercase font-bold text-zinc-400">
                        <td colSpan={records.length + 1} className="px-4 py-2 border-y border-white/10">
                          {groupTitle}
                        </td>
                      </tr>
                      {filteredParamNames.map((paramName) => {
                        const items = records.map((part) =>
                          (part.parameters ?? []).find((p: ParameterValue) => p.name === paramName),
                        );

                        const bestVal = getBestInRow(paramName, items);
                        const conditionsDiffer = checkDifferentConditions(items);
                        const meta = PARAM_SYMBOLS[paramName];
                        const label = meta?.label || humanizeParam(paramName);

                        return (
                          <tr key={paramName} className="hover:bg-white/[0.04]">
                            {/* Parameter Label Cell */}
                            <td className="px-4 py-2.5 font-sans font-medium text-white sticky left-0 bg-[#121215] border-r border-white/10">
                              <div className="flex items-center justify-between gap-2">
                                <div>
                                  <span>{label}</span>
                                  {meta?.symbol && (
                                    <span className="font-mono text-[11px] text-zinc-400 block">
                                      {meta.symbol}
                                    </span>
                                  )}
                                </div>

                                {/* "Different conditions" marker with tooltip */}
                                {conditionsDiffer && (
                                  <TooltipProvider delayDuration={100}>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <span
                                          className="cursor-help inline-flex items-center text-zinc-400 hover:text-white"
                                          aria-label="Different test conditions between parts"
                                        >
                                          <AlertTriangle className="size-3.5" />
                                        </span>
                                      </TooltipTrigger>
                                      <TooltipContent
                                        side="top"
                                        className="rounded-[4px] border border-white/20 bg-[#18181c] text-white p-2 text-xs shadow-none max-w-xs"
                                      >
                                        <div className="font-semibold mb-1">Different Conditions</div>
                                        <div>
                                          Test voltages or ambient temperatures differ between parts.
                                          Values cannot be compared directly without normalization.
                                        </div>
                                      </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                )}
                              </div>
                            </td>

                            {/* Part Columns */}
                            {records.map((part, colIdx) => {
                              const param = items[colIdx];
                              if (!param) {
                                return (
                                  <td
                                    key={part.part_id}
                                    className="px-4 py-2.5 font-mono text-zinc-500 border-r border-white/10 last:border-r-0"
                                  >
                                    -
                                  </td>
                                );
                              }

                              const isBest = bestVal !== null && param.value === bestVal;
                              const condText = formatCondition(param.condition);

                              return (
                                <td
                                  key={part.part_id}
                                  className={cn(
                                    "px-4 py-2.5 border-r border-white/10 last:border-r-0 align-top",
                                    isBest && "bg-white/[0.04]",
                                  )}
                                >
                                  <div className="space-y-1">
                                    <div className="flex items-center justify-between gap-1.5">
                                      {/* Min / Typ / Max / Value */}
                                      <span
                                        className={cn(
                                          "font-mono text-xs",
                                          isBest ? "font-bold text-white" : "text-zinc-200",
                                        )}
                                      >
                                        {param.value_min !== null && param.value_min !== undefined
                                          ? `${formatNumber(param.value_min)} ... ${formatNumber(param.value_max)} ${param.unit ?? ""}`
                                          : formatValue(param.value, param.unit)}
                                      </span>

                                      {/* Best in Row Marker */}
                                      {isBest && (
                                        <span
                                          title="Best in row"
                                          aria-label="Best in row"
                                          className="inline-flex items-center text-white"
                                        >
                                          <Award className="size-3.5 stroke-[2]" />
                                        </span>
                                      )}
                                    </div>

                                    {condText && (
                                      <div className="text-[11px] text-zinc-400 font-mono leading-tight">
                                        {condText}
                                      </div>
                                    )}

                                    {/* Source Button */}
                                    {param.source_id && (
                                      <div className="pt-1">
                                        <button
                                          type="button"
                                          onClick={() =>
                                            setActiveParamSource({
                                              partId: part.part_id,
                                              param,
                                            })
                                          }
                                          aria-label={`View source for ${label}`}
                                          className="rounded-[4px] border border-white/15 bg-white/5 px-2 py-0.5 font-mono text-[10px] text-zinc-300 hover:text-white hover:bg-white/10"
                                        >
                                          {param.page ? `p. ${param.page}` : "Source"}
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Embedded Source Viewer Sheet */}
      {activeParamSource && (
        <SourceViewer
          open={Boolean(activeParamSource)}
          onOpenChange={(open) => !open && setActiveParamSource(null)}
          partId={activeParamSource.partId}
          paramId={activeParamSource.param.param_id || activeParamSource.param.name}
          value={activeParamSource.param}
        />
      )}
    </div>
  );
}
