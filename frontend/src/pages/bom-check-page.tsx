import { useState, useRef, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Upload,
  AlertTriangle,
  Download,
  RotateCcw,
  ShieldCheck,
  ChevronDown,
  Check,
} from "lucide-react";
import { Menu } from "@animate-ui/react/primitives/base-ui/menu";
import { StatusTag } from "@/components/domain/status-tag";
import { TableSkeleton } from "@/components/loading-skeleton";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import { useBomCheck, useSearch, type BomCheckResponse } from "@/api/hooks";
import { bomSessionStore } from "@/lib/session-store";
import { downloadTextFile, toCsv } from "@/lib/format";
import { Stepper, Step } from "@/components/react-bits/Stepper";
import { cn } from "@/lib/utils";

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MiB per openapi.yaml & PLAN.md WP6

const SAMPLE_BOM = `MPN,Quantity,Reference,Description
BSC030N08NS5,4,Q1-Q4,80V 100A SuperSO8 N-channel
IRF3205S,2,Q5-Q6,55V 110A D2PAK MOSFET
UNKNOWN_PART_XYZ,1,U1,Obsolete prototype component
NCP51820,2,U2-U3,GaN driver 650V high side
`;

function parseCsvLine(line: string, delimiter = ","): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"' || char === "'") {
      if (inQuotes && line[i + 1] === char) {
        current += char;
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === delimiter && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result.map((c) => c.replace(/^["']|["']$/g, "").trim());
}

function detectCsvDelimiter(text: string): string {
  const lines = text
    .split(/\r?\n/)
    .filter((l) => l.trim() && !l.trim().startsWith("#") && !l.trim().startsWith("//"));
  if (lines.length === 0) return ",";
  const sample = lines.slice(0, 5).join("\n");
  const commaCount = (sample.match(/,/g) || []).length;
  const semiCount = (sample.match(/;/g) || []).length;
  const tabCount = (sample.match(/\t/g) || []).length;
  if (semiCount > commaCount && semiCount > tabCount) return ";";
  if (tabCount > commaCount && tabCount > semiCount) return "\t";
  return ",";
}

export function BomCheckPage() {
  const savedBom = bomSessionStore.get();
  const [file, setFile] = useState<File | null>(() => savedBom.file);
  const [fileError, setFileError] = useState<string | null>(() => savedBom.fileError);

  // Column mapping state
  const [headers, setHeaders] = useState<string[]>(() => savedBom.headers);
  const [previewRows, setPreviewRows] = useState<string[][]>(() => savedBom.previewRows);
  const [mpnCol, setMpnCol] = useState<string>(() => savedBom.mpnCol);
  const [qtyCol, setQtyCol] = useState<string>(() => savedBom.qtyCol);
  const [refCol, setRefCol] = useState<string>(() => savedBom.refCol);

  const [selectedRiskFilter, setSelectedRiskFilter] = useState<string>(() => savedBom.selectedRiskFilter);
  const [manualMatches, setManualMatches] = useState<Record<string, string>>(() => savedBom.manualMatches);

  const inputRef = useRef<HTMLInputElement | null>(null);

  const bomCheck = useBomCheck();
  const [persistedResult, setPersistedResult] = useState<BomCheckResponse | null>(() => savedBom.result);
  const result = bomCheck.data ?? persistedResult;
  const liveQueries = result?.live_queries ?? [];
  const liveDiscovered = result?.live_discovered ?? 0;
  const [activeStep, setActiveStep] = useState<number>(() => {
    if (savedBom.result) return 3;
    if (savedBom.file) return 2;
    return savedBom.activeStep || 1;
  });

  useEffect(() => {
    if (bomCheck.data) {
      setPersistedResult(bomCheck.data);
      setActiveStep(3);
      bomSessionStore.set({ result: bomCheck.data, activeStep: 3 });
    }
  }, [bomCheck.data]);

  // Catalog query for manual replacement dropdown
  const partsQuery = useSearch({ query: "mosfet", limit: 20 });

  // Handle client-side CSV preview & header detection
  const parsePreview = (text: string) => {
    const rawLines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.length > 0 && !l.startsWith("#") && !l.startsWith("//"));
    if (rawLines.length < 1) {
      setFileError("The uploaded CSV file is empty.");
      return;
    }

    const delimiter = detectCsvDelimiter(text);
    const firstLine = rawLines[0] ?? "";
    const detectedHeaders = parseCsvLine(firstLine, delimiter);
    setHeaders(detectedHeaders);

    // Auto-detect columns (including EDA / KiCad 'Value' column)
    const lowerHeaders = detectedHeaders.map((h) => h.toLowerCase().trim());
    const mpnIdx = lowerHeaders.findIndex((h) =>
      [
        "mpn",
        "part",
        "part_number",
        "part number",
        "part no",
        "part no.",
        "component",
        "value",
        "val",
        "device",
        "item",
        "comment",
        "designation",
        "order code",
        "article",
        "catalog no",
        "lcsc part #",
        "mfr part number",
        "mfr part no",
        "pn",
        "p/n",
      ].includes(h),
    );
    if (mpnIdx !== -1) setMpnCol(detectedHeaders[mpnIdx] || "");

    const qtyIdx = lowerHeaders.findIndex((h) =>
      ["qty", "quantity", "count", "amount", "total qty", "pcs", "units", "quantity ordered"].includes(h),
    );
    if (qtyIdx !== -1) setQtyCol(detectedHeaders[qtyIdx] || "");

    const refIdx = lowerHeaders.findIndex((h) =>
      ["ref", "reference", "designator", "designators", "refdes", "refs", "loc", "location"].includes(h),
    );
    if (refIdx !== -1) setRefCol(detectedHeaders[refIdx] || "");

    const rows = rawLines.slice(1, 11).map((line) => parseCsvLine(line, delimiter));
    setPreviewRows(rows);
    bomSessionStore.set({ headers: detectedHeaders, previewRows: rows });
  };

  const handleFileChange = async (selectedFile: File | null) => {
    setFileError(null);
    if (!selectedFile) return;

    if (!selectedFile.name.endsWith(".csv")) {
      setFileError("Only .csv files are supported. Please upload a comma-separated BOM export.");
      return;
    }

    if (selectedFile.size > MAX_FILE_SIZE) {
      setFileError("File exceeds the 5 MiB payload limit specified in the API contract.");
      return;
    }

    setFile(selectedFile);
    bomSessionStore.set({ file: selectedFile, fileName: selectedFile.name, activeStep: 2 });
    bomCheck.mutate(selectedFile);

    try {
      if (typeof selectedFile.text === "function") {
        const text = await selectedFile.text();
        parsePreview(text);
        bomSessionStore.set({ fileContent: text });
      } else {
        const reader = new FileReader();
        reader.onload = (e) => {
          const text = e.target?.result as string;
          parsePreview(text);
          bomSessionStore.set({ fileContent: text });
        };
        reader.readAsText(selectedFile);
      }
    } catch {
      setFileError("Could not parse CSV content. Check file encoding.");
    }
  };

  const handleLoadSample = () => {
    const blob = new Blob([SAMPLE_BOM], { type: "text/csv" });
    const sampleFile = new File([blob], "demo-bom.csv", { type: "text/csv" });
    void handleFileChange(sampleFile);
  };

  const handleReset = () => {
    setFile(null);
    setFileError(null);
    setHeaders([]);
    setPreviewRows([]);
    setPersistedResult(null);
    bomCheck.reset();
    setActiveStep(1);
    bomSessionStore.reset();
  };

  // Filter lines by selected risk
  const displayLines = useMemo(() => {
    if (!result?.lines) return [];
    if (selectedRiskFilter === "all") return result.lines;
    return result.lines.filter((line) => {
      if (selectedRiskFilter === "not_found") return !line.matched;
      return (line.risks ?? []).some(
        (r) => r.severity?.toLowerCase() === selectedRiskFilter || r.code?.toLowerCase() === selectedRiskFilter,
      );
    });
  }, [result?.lines, selectedRiskFilter]);

  // Run check with explicit column mapping if selected
  const handleRunCheck = async () => {
    setActiveStep(3);
    if (!file) return;

    try {
      let text = "";
      if (typeof file.text === "function") {
        text = await file.text();
      } else {
        text = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve((e.target?.result as string) || "");
          reader.readAsText(file);
        });
      }

      if (text) {
        const delimiter = detectCsvDelimiter(text);
        const rawLines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
        let headerIdx = rawLines.findIndex((l) => !l.startsWith("#") && !l.startsWith("//"));
        if (headerIdx === -1) headerIdx = 0;

        const originalCols = parseCsvLine(rawLines[headerIdx] || "", delimiter);
        const mpnIndex = mpnCol ? originalCols.indexOf(mpnCol) : 0;
        const qtyIndex = qtyCol ? originalCols.indexOf(qtyCol) : -1;
        const refIndex = refCol ? originalCols.indexOf(refCol) : -1;

        if (mpnIndex !== -1) {
          const mappedRows: string[] = ['"MPN","Qty","Reference"'];
          for (let i = headerIdx + 1; i < rawLines.length; i++) {
            const rowLine = rawLines[i];
            if (!rowLine || rowLine.startsWith("#") || rowLine.startsWith("//")) continue;
            const cells = parseCsvLine(rowLine, delimiter);
            const cellMpn = (cells[mpnIndex] || cells[0] || "").trim();
            if (!cellMpn) continue;
            const cellQty =
              qtyIndex >= 0 && cells[qtyIndex]
                ? cells[qtyIndex].replace(/[^0-9.]/g, "") || "1"
                : "1";
            const cellRef = refIndex >= 0 && cells[refIndex] ? cells[refIndex] : `R${i}`;
            mappedRows.push(
              `"${cellMpn.replace(/"/g, '""')}","${cellQty}","${cellRef.replace(/"/g, '""')}"`,
            );
          }
          const mappedBlob = new Blob([mappedRows.join("\n")], { type: "text/csv" });
          const mappedFile = new File([mappedBlob], file.name, { type: "text/csv" });
          bomCheck.mutate(mappedFile);
          return;
        }
      }
    } catch {
      // Fall back to original file if text extraction fails
    }
    bomCheck.mutate(file);
  };

  // Export report as CSV
  const handleExportReport = () => {
    if (!result?.lines) return;
    const rows = result.lines.map((line) => ({
      Line: line.line_number,
      MPN: line.mpn,
      MatchedPart: line.matched_part_id ?? "NOT FOUND",
      Quantity: line.quantity,
      Risks: (line.risks ?? []).map((r) => `${r.code} (${r.severity})`).join("; ") || "NONE",
      ManualMatch: manualMatches[line.mpn] || "",
    }));

    const csv = toCsv(rows);
    downloadTextFile(`partpilot-bom-report-${Date.now()}.csv`, csv, "text/csv;charset=utf-8;");
  };

  const notFoundLines = (result?.lines ?? []).filter((l) => !l.matched);

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-white" />
            <h1 className="font-heading text-2xl font-semibold tracking-tight text-white">
              BOM Risk & Lifecycle Check
            </h1>
          </div>
          <p className="text-xs text-zinc-400 font-sans mt-1">
            Audit your bill of materials for obsolescence, single-source dependencies, and inventory lead times.
          </p>
        </div>

        {result && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 transition-none"
            >
              <RotateCcw className="size-3.5" />
              <span>Check another BOM</span>
            </button>
            <button
              type="button"
              onClick={handleExportReport}
              className="inline-flex items-center gap-1.5 rounded-[8px] bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200 transition-none"
            >
              <Download className="size-3.5" />
              <span>Export Report</span>
            </button>
          </div>
        )}
      </div>

      {/* Interactive Stepper Workflow */}
      <Stepper
        step={activeStep}
        onStepChange={(newStep) => setActiveStep(newStep)}
        showFooter={false}
        frame={false}
        theme="dark"
        indicator="numbers"
        width="100%"
        className="w-full"
      >
        <Step title="Upload CSV" description="Drop or select BOM">
          <div className="space-y-6 w-full pt-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
              <div>
                <h2 className="font-heading text-base font-semibold text-white">Upload Bill of Materials</h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Accepts comma-separated (.csv) design exports up to 5 MiB.
                </p>
              </div>
              <button
                type="button"
                onClick={handleLoadSample}
                className="rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 cursor-pointer"
              >
                Load Demo BOM
              </button>
            </div>

            {/* Dashed Drop Zone */}
            <div
              onClick={() => inputRef.current?.click()}
              className="flex flex-col items-center justify-center rounded-[8px] border-2 border-dashed border-white/20 bg-white/[0.02] p-10 text-center cursor-pointer hover:bg-white/[0.06] transition-colors"
            >
              <Upload className="size-8 text-zinc-400 mb-2" />
              <div className="font-medium text-xs text-white mb-1">
                Click to select or drag and drop BOM CSV
              </div>
              <div className="text-[11px] text-zinc-400 font-mono">
                Maximum file size: 5 MiB (Contract WP6 limit)
              </div>

              <label htmlFor="bom-file-input" className="sr-only">
                BOM file (CSV)
              </label>
              <input
                id="bom-file-input"
                aria-label="BOM file (CSV)"
                ref={inputRef}
                type="file"
                accept=".csv"
                onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                className="hidden"
              />
            </div>

            {file && (
              <div className="rounded-[4px] border border-white/20 bg-white/5 p-3 text-xs text-zinc-200 font-mono flex items-center justify-between">
                <span>Loaded file: <strong className="text-white">{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)</span>
                <button
                  type="button"
                  onClick={() => setActiveStep(2)}
                  className="rounded-[6px] bg-white px-2.5 py-1 text-xs font-medium text-black hover:bg-zinc-200"
                >
                  Configure columns &rarr;
                </button>
              </div>
            )}

            {fileError && (
              <div className="rounded-[4px] border border-white/20 bg-white/5 p-3 text-xs text-white font-mono flex items-center gap-2">
                <AlertTriangle className="size-4 shrink-0" />
                <span>{fileError}</span>
              </div>
            )}

            {/* Privacy & Retention Line */}
            <div className="text-[11px] text-zinc-400 font-sans border-t border-white/10 pt-3">
              BOM files are processed in-memory for catalog lookup and risk calculation. In accordance with the system specification, uploaded bill of materials files are never permanently retained on the server.
            </div>
          </div>
        </Step>

        <Step title="Map Columns" description="Inspect CSV columns">
          {file && previewRows.length > 0 ? (
            <div className="space-y-6 w-full pt-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <h3 className="font-heading text-sm font-semibold text-white">
                  Step 2: Map CSV Columns ({file.name})
                </h3>
                <span className="font-mono text-xs text-zinc-400">Previewing first 10 rows</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <ColumnDropdownMenu
                  label="MPN Column (Required)"
                  value={mpnCol}
                  options={headers.map((h) => ({ label: h, value: h }))}
                  onChange={setMpnCol}
                  required
                />

                <ColumnDropdownMenu
                  label="Quantity Column (Optional)"
                  value={qtyCol}
                  options={[
                    { label: "None", value: "" },
                    ...headers.map((h) => ({ label: h, value: h })),
                  ]}
                  onChange={setQtyCol}
                />

                <ColumnDropdownMenu
                  label="Reference Designator (Optional)"
                  value={refCol}
                  options={[
                    { label: "None", value: "" },
                    ...headers.map((h) => ({ label: h, value: h })),
                  ]}
                  onChange={setRefCol}
                />
              </div>

              <div className="overflow-x-auto border-b border-white/10 mt-3">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-white/[0.02] text-[11px] uppercase text-zinc-400 border-b border-white/10">
                    <tr>
                      {headers.map((h) => (
                        <th key={h} className="px-3 py-2">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {previewRows.map((row, rIdx) => (
                      <tr key={rIdx} className="hover:bg-white/[0.04]">
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="px-3 py-1.5 text-zinc-200">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setActiveStep(1)}
                  className="rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:bg-white/10 cursor-pointer"
                >
                  &larr; Back to Upload
                </button>
                <button
                  type="button"
                  onClick={handleRunCheck}
                  disabled={bomCheck.isPending}
                  className="rounded-[8px] bg-white px-4 py-2 text-xs font-medium text-black hover:bg-zinc-200 disabled:opacity-40 cursor-pointer inline-flex items-center gap-2"
                >
                  {bomCheck.isPending ? (
                    <>
                      <MotionGridLoader size="xs" variant="default" />
                      <span>Analyzing BOM...</span>
                    </>
                  ) : (
                    <span>Run check &rarr;</span>
                  )}
                </button>
              </div>
            </div>
          ) : (
            <div className="py-12 border-b border-white/10 text-center space-y-3 w-full">
              <p className="text-sm text-zinc-400">Please upload a BOM CSV in Step 1 first to map columns.</p>
              <button
                type="button"
                onClick={() => setActiveStep(1)}
                className="rounded-[8px] bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200 cursor-pointer"
              >
                Go to Step 1: Upload CSV
              </button>
            </div>
          )}
        </Step>

        <Step title="Risk Audit" description="Obsolescence & supply analysis">
          {bomCheck.isPending && (
            <TableSkeleton
              rows={6}
              cols={6}
              title="Analyzing Bill of Materials…"
              description="Scanning lifecycle stages, calculating obsolescence risk, and checking distributor inventory."
            />
          )}

          {result ? (
            <div className="space-y-8 w-full pt-4">
              {/* Summary Row - Clean hairline separation */}
              <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-white/10 border-y border-white/10 py-6">
                <div className="sm:px-6 py-2 space-y-1 first:sm:pl-0">
                  <div className="font-mono text-xs uppercase tracking-wider text-zinc-400 mb-1">
                    Lines Checked
                  </div>
                  <div className="font-mono text-3xl font-semibold text-white">
                    {result.total_lines ?? 0}
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">Processed from CSV</div>
                </div>

                <div className="sm:px-6 py-2 space-y-1">
                  <div className="font-mono text-xs uppercase tracking-wider text-zinc-400 mb-1">
                    Lines at Risk
                  </div>
                  <div className="font-mono text-3xl font-semibold text-white">
                    {result.risk_count ?? 0}
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Severity: {result.highest_severity ? result.highest_severity.toUpperCase() : "NONE"}
                  </div>
                </div>

                <div className="sm:px-6 py-2 space-y-1 last:sm:pr-0">
                  <div className="font-mono text-xs uppercase tracking-wider text-zinc-400 mb-1">
                    Not Found
                  </div>
                  <div className="font-mono text-3xl font-semibold text-white">
                    {result.unmatched_lines ?? 0}
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">Require manual replacement</div>
                </div>
              </div>

              {(liveDiscovered > 0 || liveQueries.length > 0) && (
                <div className="rounded-[8px] border border-white/15 bg-white/[0.03] p-4 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-mono uppercase tracking-wider text-white">
                        AI-assisted live enrichment
                      </div>
                      <p className="mt-1 text-[11px] text-zinc-400">
                        Search plans were generated per BOM line and sent through SearXNG before risk scoring.
                      </p>
                    </div>
                    <span className="text-[11px] font-mono text-zinc-300">
                      {liveDiscovered} candidates ingested
                    </span>
                  </div>
                  {liveQueries.length > 0 && (
                    <details className="text-[11px] text-zinc-400">
                      <summary className="cursor-pointer text-zinc-300 hover:text-white">
                        View generated search queries ({liveQueries.length})
                      </summary>
                      <ul className="mt-2 space-y-1 pl-4 font-mono list-disc">
                        {liveQueries.slice(0, 12).map((query) => (
                          <li key={query}>{query}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}

              {/* Filter by Risk Pill Toggles */}
              <div className="flex flex-wrap items-center gap-2 select-none">
                <span className="text-xs font-mono uppercase tracking-wider text-zinc-400 mr-2">
                  Filter risk:
                </span>
                {["all", "not_found", "critical", "high", "medium", "low"].map((riskKey) => (
                  <button
                    key={riskKey}
                    type="button"
                    onClick={() => setSelectedRiskFilter(riskKey)}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium transition-none capitalize cursor-pointer",
                      selectedRiskFilter === riskKey
                        ? "border border-white bg-white text-black"
                        : "border border-white/20 bg-transparent text-white hover:bg-white/10",
                    )}
                  >
                    {riskKey.replace("_", " ")}
                  </button>
                ))}
              </div>

              {/* Results Table (Unboxed, clean separation) */}
              <div className="space-y-4 w-full">
                <div className="overflow-x-auto border-b border-white/10">
                  <table className="w-full text-left text-xs font-sans">
                    <thead className="bg-white/[0.02] text-[11px] font-mono uppercase text-zinc-400 border-b border-white/10 select-none">
                      <tr>
                        <th className="px-3 py-2.5 w-12 font-mono">Line</th>
                        <th className="px-3 py-2.5">MPN</th>
                        <th className="px-3 py-2.5">Matched Component</th>
                        <th className="px-3 py-2.5">Status</th>
                        <th className="px-3 py-2.5 font-mono">Qty</th>
                        <th className="px-3 py-2.5">Risk Flags</th>
                        <th className="px-3 py-2.5 text-right">Alternatives</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {displayLines.map((line) => {
                        const lineRisks = line.risks ?? [];
                        const manualMatch = manualMatches[line.mpn];

                        return (
                          <tr key={line.line_number} className="hover:bg-white/[0.04]">
                            <td className="px-3 py-2.5 font-mono text-zinc-400">
                              #{line.line_number}
                            </td>

                            <td className="px-3 py-2.5 font-mono font-medium text-white">
                              {line.mpn}
                              {manualMatch && (
                                <div className="text-[11px] text-zinc-400 font-sans">
                                  Mapped: <span className="font-mono font-bold text-white">{manualMatch}</span>
                                </div>
                              )}
                            </td>

                            <td className="px-3 py-2.5 font-sans">
                              {line.matched_part_id ? (
                                <Link
                                  to={`/parts/${line.matched_part_id}`}
                                  className="text-white underline hover:text-zinc-300 font-mono text-xs"
                                >
                                  {line.matched_part_id}
                                </Link>
                              ) : (
                                <span className="font-mono text-zinc-400">Unmatched</span>
                              )}
                            </td>

                            <td className="px-3 py-2.5">
                              <StatusTag status={line.matched ? "active" : "unknown"} type="lifecycle" />
                            </td>

                            <td className="px-3 py-2.5 font-mono text-zinc-300">{line.quantity}</td>

                            <td className="px-3 py-2.5">
                              <div className="flex flex-wrap gap-1.5">
                                {lineRisks.map((risk, rIdx) => (
                                  <div
                                    key={rIdx}
                                    className="inline-flex items-center gap-1 rounded-[4px] border border-white/20 bg-white/5 px-2 py-0.5 text-[11px] font-mono text-white"
                                    title={risk.message}
                                  >
                                    <span>Risk: {risk.code}</span>
                                    <span className="text-[10px] text-zinc-400">({risk.severity})</span>
                                  </div>
                                ))}
                                {lineRisks.length === 0 && (
                                  <span className="text-[11px] font-mono text-zinc-400">No risks</span>
                                )}
                              </div>
                            </td>

                            <td className="px-3 py-2.5 text-right">
                              {line.matched_part_id ? (
                                <Link
                                  to={`/parts/${line.matched_part_id}?tab=alternatives`}
                                  className="text-white underline hover:text-zinc-300 text-xs"
                                >
                                  Alternatives
                                </Link>
                              ) : (
                                <Link
                                  to={`/search?q=${encodeURIComponent(line.mpn)}`}
                                  className="text-white underline hover:text-zinc-300 text-xs"
                                >
                                  Find match
                                </Link>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Display list of all individual risks for audit compliance */}
                <div className="mt-4 pt-4 border-t border-white/10 text-xs">
                  <h4 className="font-mono text-xs uppercase font-bold tracking-wider text-zinc-400 mb-2">
                    Detailed Risk Log ({result.risks?.length ?? 0} flags)
                  </h4>
                  <div className="divide-y divide-white/5">
                    {(result.risks ?? []).map((risk, idx) => (
                      <div key={idx} className="py-1.5 flex items-start justify-between gap-4 font-mono text-[11px]">
                        <div>
                          <span className="font-bold text-white mr-2">{risk.code}</span>
                          <span className="text-zinc-400">{risk.message}</span>
                        </div>
                        <span className="uppercase text-zinc-400">{risk.severity}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* "Not found" lines manual match panel (Clean unboxed separation) */}
              {notFoundLines.length > 0 && (
                <div className="space-y-4 w-full pt-6 border-t border-white/10">
                  <h3 className="font-heading text-sm font-semibold text-white">
                    Manual Replacement Picker for Unmatched Lines
                  </h3>
                  <p className="text-xs text-zinc-400">
                    Pick a verified component from the catalog to substitute for unindexed parts. Matches apply to exported reports.
                  </p>

                  <div className="space-y-3">
                    {notFoundLines.map((line) => (
                      <div
                        key={line.line_number}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-[6px] border border-white/10 bg-white/5 p-3"
                      >
                        <div>
                          <span className="font-mono font-medium text-white mr-2">{line.mpn}</span>
                          <span className="text-xs text-zinc-400 font-sans">
                            (Needed: {line.quantity} units)
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <select
                            value={manualMatches[line.mpn] || ""}
                            onChange={(e) =>
                              setManualMatches({ ...manualMatches, [line.mpn]: e.target.value })
                            }
                            className="rounded-[4px] border border-white/20 bg-black p-1.5 font-mono text-xs text-white outline-none"
                          >
                            <option value="" className="bg-black text-white">Select replacement...</option>
                            {(partsQuery.data?.results ?? []).map((p) => (
                              <option key={p.part_id} value={p.mpn} className="bg-black text-white">
                                {p.mpn} ({p.manufacturer})
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : !bomCheck.isPending ? (
            <div className="rounded-[12px] bg-[#121215] text-white p-8 border border-white/10 shadow-none text-center space-y-3 w-full">
              <p className="text-sm text-zinc-400">No BOM analysis run yet. Upload and submit a BOM file to inspect supply risks.</p>
              <button
                type="button"
                onClick={() => setActiveStep(1)}
                className="rounded-[8px] bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200"
              >
                Go to Step 1: Upload CSV
              </button>
            </div>
          ) : null}
        </Step>
      </Stepper>
    </div>
  );
}

function ColumnDropdownMenu({
  label,
  value,
  options,
  onChange,
  required = false,
}: {
  label: string;
  value: string;
  options: { label: string; value: string }[];
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const currentOption = options.find((o) => o.value === value);
  const displayLabel = currentOption ? currentOption.label : value || (required ? "Select column..." : "None");

  return (
    <div className="space-y-1.5 w-full">
      <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400">
        {label}
      </label>

      <Menu.Root>
        <Menu.Trigger
          type="button"
          className="w-full flex items-center justify-between gap-2 rounded-[6px] border border-white/15 bg-white/5 hover:bg-white/10 hover:border-white/25 px-3 py-2 font-mono text-xs text-white transition-colors focus:outline-none focus:border-white/40 cursor-pointer text-left"
        >
          <span className="truncate">{displayLabel}</span>
          <ChevronDown className="size-3.5 text-zinc-400 shrink-0" />
        </Menu.Trigger>

        <Menu.Portal>
          <Menu.Positioner sideOffset={4} className="z-50">
            <Menu.Popup className="min-w-[var(--anchor-width,180px)] max-h-60 overflow-y-auto rounded-[8px] border border-white/15 bg-[#121215] p-1 text-xs text-white shadow-2xl focus:outline-none space-y-0.5">
              <Menu.RadioGroup value={value} onValueChange={(val) => onChange(val)}>
                {options.map((opt) => (
                  <Menu.RadioItem
                    key={opt.value}
                    value={opt.value}
                    closeOnClick
                    className="relative flex items-center justify-between gap-3 rounded-[5px] px-2.5 py-1.5 font-mono text-xs text-zinc-300 hover:text-white hover:bg-white/10 data-[highlighted]:bg-white/10 data-[highlighted]:text-white cursor-pointer outline-none select-none transition-colors"
                  >
                    <span className="truncate">{opt.label}</span>
                    <Menu.RadioItemIndicator animation="pop" className="text-white shrink-0">
                      <Check className="size-3.5 text-white" />
                    </Menu.RadioItemIndicator>
                  </Menu.RadioItem>
                ))}
              </Menu.RadioGroup>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </div>
  );
}
