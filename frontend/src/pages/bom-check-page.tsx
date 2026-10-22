import { useRef, useState } from "react";
import { Upload } from "lucide-react";
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
import { SeverityBadge } from "@/components/status-badge";
import { ErrorState } from "@/components/error-state";
import { useBomCheck } from "@/api/hooks";
import { SEVERITY_ORDER } from "@/lib/status";

/** The BOM check page (FR-14). */
export function BomCheckPage() {
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bomCheck = useBomCheck();

  const handleFile = (next: File | null) => {
    setFile(next);
    if (next) bomCheck.mutate(next);
  };

  const result = bomCheck.data;
  const counts = result
    ? SEVERITY_ORDER.map((severity) => ({
        severity,
        count: (result.risks ?? []).filter((risk) => risk.severity === severity).length,
      })).filter((entry) => entry.count > 0)
    : [];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">BOM check</h1>
        <p className="text-sm text-muted-foreground">
          Upload a BOM CSV. Every line is matched against the part database and the risks are listed
          with a severity.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-1.5">
            <Label htmlFor="bom-file">BOM file (CSV)</Label>
            <Input
              id="bom-file"
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => inputRef.current?.click()}
              disabled={bomCheck.isPending}
            >
              <Upload className="size-4" />
              {bomCheck.isPending ? "Checking…" : "Choose a file"}
            </Button>
            {file && <span className="text-sm text-muted-foreground">{file.name}</span>}
          </div>
        </CardContent>
      </Card>

      {bomCheck.isError && (
        <ErrorState
          title="The BOM could not be checked"
          error={bomCheck.error}
          onRetry={() => file && bomCheck.mutate(file)}
        />
      )}

      {result && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">Lines</dt>
                  <dd className="text-xl font-semibold tabular-nums">{result.total_lines ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">Matched</dt>
                  <dd className="text-xl font-semibold tabular-nums">
                    {result.matched_lines ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    Unmatched
                  </dt>
                  <dd className="text-xl font-semibold tabular-nums">
                    {result.unmatched_lines ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">Risks</dt>
                  <dd className="text-xl font-semibold tabular-nums">{result.risk_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">Highest</dt>
                  <dd className="text-xl font-semibold">
                    <SeverityBadge severity={result.highest_severity} />
                  </dd>
                </div>
              </dl>
              {counts.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {counts.map((entry) => (
                    <span key={entry.severity} className="flex items-center gap-1 text-sm">
                      <SeverityBadge severity={entry.severity} />
                      <span className="tabular-nums text-muted-foreground">{entry.count}</span>
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Risks</CardTitle>
            </CardHeader>
            <CardContent>
              {(result.risks ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No risk was found in this BOM.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Severity</TableHead>
                        <TableHead>Code</TableHead>
                        <TableHead>MPN</TableHead>
                        <TableHead>Message</TableHead>
                        <TableHead>Suggestion</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(result.risks ?? []).map((risk, index) => (
                        <TableRow key={`${risk.code}-${index}`}>
                          <TableCell>
                            <SeverityBadge severity={risk.severity} />
                          </TableCell>
                          <TableCell className="font-mono">{risk.code}</TableCell>
                          <TableCell className="font-mono">{risk.mpn ?? "-"}</TableCell>
                          <TableCell>{risk.message}</TableCell>
                          <TableCell className="text-muted-foreground">
                            {risk.suggestion ?? "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
