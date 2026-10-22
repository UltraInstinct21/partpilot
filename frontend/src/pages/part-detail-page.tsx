import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, PlayCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { LifecycleBadge } from "@/components/lifecycle-badge";
import { StatusBadge } from "@/components/status-badge";
import { SourceViewer } from "@/components/source-viewer";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/loading-skeleton";
import { useAlternatives, useJob, usePart, useStartExtractionJob } from "@/api/hooks";
import type { ParameterValue } from "@/api/hooks";
import { formatCondition, formatDate, formatParameterValue, humanizeParam } from "@/lib/format";

/** The part detail page. Every value shows its unit, condition and confidence. */
export function PartDetailPage() {
  const { partId } = useParams<{ partId: string }>();
  const partQuery = usePart(partId);
  const alternativesQuery = useAlternatives(partId);
  const startJob = useStartExtractionJob();
  const [jobId, setJobId] = useState<string | undefined>(undefined);
  const jobQuery = useJob(jobId);
  const [sourceTarget, setSourceTarget] = useState<{
    paramId: string;
    value: ParameterValue;
  } | null>(null);

  const part = partQuery.data;
  const parameters = useMemo(() => part?.parameters ?? [], [part]);

  if (partQuery.isPending) {
    return <TableSkeleton rows={8} cols={6} />;
  }

  if (partQuery.isError || !part) {
    return (
      <ErrorState
        title="The part could not be loaded"
        error={partQuery.error}
        onRetry={() => void partQuery.refetch()}
      />
    );
  }

  const handleStartJob = () => {
    startJob.mutate(
      { part_id: part.part_id },
      {
        onSuccess: (job) => setJobId(job.job_id),
      },
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link to="/">
            <ArrowLeft className="size-4" />
            Back to search
          </Link>
        </Button>
      </div>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{part.mpn}</h1>
          <LifecycleBadge status={part.lifecycle_status} />
          <Badge variant="secondary">{part.family}</Badge>
          {part.package && <Badge variant="outline">{part.package}</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">
          {part.manufacturer}
          {part.description ? ` · ${part.description}` : ""}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {part.datasheet_url && (
            <Button asChild variant="outline" size="sm">
              <a href={part.datasheet_url} target="_blank" rel="noreferrer noopener">
                Datasheet
                <ExternalLink className="size-4" />
              </a>
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleStartJob}
            disabled={startJob.isPending}
          >
            <PlayCircle className="size-4" />
            Start extraction
          </Button>
          {jobQuery.data && (
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              Job {jobQuery.data.job_id}: {jobQuery.data.state}
              <Progress value={(jobQuery.data.progress ?? 0) * 100} className="h-1.5 w-24" />
            </span>
          )}
        </div>
      </header>

      <Tabs defaultValue="specs">
        <TabsList>
          <TabsTrigger value="specs">Specs</TabsTrigger>
          <TabsTrigger value="offers">Offers</TabsTrigger>
          <TabsTrigger value="alternatives">Alternatives</TabsTrigger>
        </TabsList>

        <TabsContent value="specs">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Parameters ({parameters.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Parameter</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead>Condition</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Method</TableHead>
                      <TableHead>Page</TableHead>
                      <TableHead>Source</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {parameters.map((value) => (
                      <TableRow key={value.param_id ?? value.name}>
                        <TableCell className="font-medium">{humanizeParam(value.name)}</TableCell>
                        <TableCell className="font-mono tabular-nums">
                          {formatParameterValue(value)}
                        </TableCell>
                        <TableCell className="text-muted-foreground">{value.unit ?? "-"}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatCondition(value.condition) || "-"}
                        </TableCell>
                        <TableCell>
                          <ConfidenceBadge confidence={value.confidence} />
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={value.status} />
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {value.method ?? "-"}
                        </TableCell>
                        <TableCell className="tabular-nums text-muted-foreground">
                          {value.page ?? "-"}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col items-start gap-1">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                setSourceTarget({ paramId: value.param_id ?? value.name, value })
                              }
                            >
                              View source
                            </Button>
                            <span className="font-mono text-[11px] text-muted-foreground">
                              {value.source_id ?? "-"}
                            </span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="offers">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Offers ({(part.offers ?? []).length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Distributor</TableHead>
                      <TableHead>SKU</TableHead>
                      <TableHead>Stock</TableHead>
                      <TableHead>Unit price</TableHead>
                      <TableHead>Lead time</TableHead>
                      <TableHead>Fetched</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(part.offers ?? []).map((offer) => (
                      <TableRow key={`${offer.distributor}-${offer.sku ?? ""}`}>
                        <TableCell className="font-medium">{offer.distributor}</TableCell>
                        <TableCell className="font-mono">{offer.sku ?? "-"}</TableCell>
                        <TableCell className="tabular-nums">{offer.stock ?? "-"}</TableCell>
                        <TableCell className="tabular-nums">
                          {offer.unit_price !== null && offer.unit_price !== undefined
                            ? `${offer.unit_price} ${offer.currency}`
                            : "-"}
                        </TableCell>
                        <TableCell>
                          {offer.lead_time_days !== null && offer.lead_time_days !== undefined
                            ? `${offer.lead_time_days} d`
                            : "-"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(offer.fetched_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alternatives">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Alternatives</CardTitle>
            </CardHeader>
            <CardContent>
              {alternativesQuery.isPending && <TableSkeleton rows={4} cols={3} />}
              {alternativesQuery.isError && (
                <ErrorState
                  title="The alternatives could not be loaded"
                  error={alternativesQuery.error}
                  onRetry={() => void alternativesQuery.refetch()}
                />
              )}
              {(alternativesQuery.data ?? []).length === 0 && !alternativesQuery.isPending && (
                <p className="text-sm text-muted-foreground">No alternative was found.</p>
              )}
              <ol className="space-y-3">
                {(alternativesQuery.data ?? []).map((alternative) => (
                  <li
                    key={alternative.part.part_id}
                    className="rounded-lg border border-border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">#{alternative.rank}</span>
                      <Link
                        to={`/parts/${alternative.part.part_id}`}
                        className="font-medium underline underline-offset-4"
                      >
                        {alternative.part.mpn}
                      </Link>
                      <span className="text-sm text-muted-foreground">
                        {alternative.part.manufacturer}
                      </span>
                      <LifecycleBadge status={alternative.part.lifecycle_status} />
                      <Badge variant="secondary" className="font-mono">
                        score {alternative.score}
                      </Badge>
                    </div>
                    {alternative.reason && (
                      <p className="mt-1 text-sm text-muted-foreground">{alternative.reason}</p>
                    )}
                    {alternative.differences &&
                      Object.entries(alternative.differences).map(([name, values]) => (
                        <p key={name} className="mt-1 font-mono text-xs">
                          {name}: {String(values.reference ?? "-")} →{" "}
                          {String(values.candidate ?? "-")}
                        </p>
                      ))}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {sourceTarget && (
        <SourceViewer
          open
          onOpenChange={(open) => !open && setSourceTarget(null)}
          partId={part.part_id}
          paramId={sourceTarget.paramId}
          value={sourceTarget.value}
        />
      )}
    </div>
  );
}
