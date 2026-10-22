import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { createColumnHelper, flexRender, type SortingState, useTable } from "@tanstack/react-table";
import { toast } from "sonner";
import { Check, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/loading-skeleton";
import { useReviewDecision, useReviewQueue } from "@/api/hooks";
import type { ReviewItem } from "@/api/hooks";
import { sortingFeatures } from "@/lib/table";
import { formatNumber, humanizeParam } from "@/lib/format";

const correctionSchema = z.object({
  value: z
    .string()
    .min(1, "A value is required")
    .refine((raw) => !Number.isNaN(Number(raw)), "The value must be a number"),
});

type CorrectionValues = z.infer<typeof correctionSchema>;

const helper = createColumnHelper<typeof sortingFeatures, ReviewItem>();

/** The review queue: the values that wait for a human decision. */
export function ReviewQueuePage() {
  const queueQuery = useReviewQueue();
  const decision = useReviewDecision();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [correcting, setCorrecting] = useState<ReviewItem | null>(null);

  const items = useMemo(() => queueQuery.data ?? [], [queueQuery.data]);

  const columns = useMemo(
    () =>
      helper.columns([
        helper.accessor("mpn", { header: "MPN" }),
        helper.accessor("manufacturer", { header: "Manufacturer" }),
        helper.accessor("name", {
          header: "Parameter",
          cell: (info) => humanizeParam(info.getValue()),
        }),
        helper.accessor("value", {
          header: "Value",
          cell: (info) =>
            info.getValue() === null || info.getValue() === undefined
              ? "-"
              : formatNumber(info.getValue()),
        }),
        helper.accessor("unit", {
          header: "Unit",
          cell: (info) => info.getValue() ?? "-",
        }),
        helper.accessor("confidence", {
          header: "Confidence",
          cell: (info) => <ConfidenceBadge confidence={info.getValue()} />,
        }),
        helper.accessor("reasons", {
          header: "Reasons",
          cell: (info) => {
            const reasons = info.getValue() ?? [];
            return reasons.length === 0 ? "-" : reasons.join("; ");
          },
        }),
        helper.display({
          id: "actions",
          header: "Actions",
          cell: (info) => {
            const item = info.row.original;
            return (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() =>
                    decision.mutate(
                      { paramId: item.param_id, decision: { action: "accept" } },
                      {
                        onSuccess: () => toast.success(`${item.name} was accepted`),
                      },
                    )
                  }
                  disabled={decision.isPending}
                >
                  <Check className="size-4" />
                  Accept
                </Button>
                <Button size="sm" variant="outline" onClick={() => setCorrecting(item)}>
                  <Pencil className="size-4" />
                  Correct
                </Button>
              </div>
            );
          },
        }),
      ]),
    [decision],
  );

  const table = useTable({
    features: sortingFeatures,
    columns,
    data: items,
    state: { sorting },
    onSortingChange: setSorting,
  });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
        <p className="text-sm text-muted-foreground">
          Every value with a low confidence waits here. Accept it or correct it with the value that
          the datasheet really states.
        </p>
      </header>

      {queueQuery.isPending && <TableSkeleton rows={6} cols={7} />}
      {queueQuery.isError && (
        <ErrorState
          title="The review queue could not be loaded"
          error={queueQuery.error}
          onRetry={() => void queueQuery.refetch()}
        />
      )}

      {queueQuery.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{queueQuery.data.length} values to review</CardTitle>
          </CardHeader>
          <CardContent>
            {queueQuery.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing to review.</p>
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
          </CardContent>
        </Card>
      )}

      <CorrectionDialog
        item={correcting}
        onClose={() => setCorrecting(null)}
        onSubmit={(value) => {
          if (!correcting) return;
          decision.mutate(
            { paramId: correcting.param_id, decision: { action: "correct", value } },
            {
              onSuccess: () => {
                toast.success(`${correcting.name} was corrected`);
                setCorrecting(null);
              },
            },
          );
        }}
      />
    </div>
  );
}

function CorrectionDialog({
  item,
  onClose,
  onSubmit,
}: {
  item: ReviewItem | null;
  onClose: () => void;
  onSubmit: (value: number) => void;
}) {
  const form = useForm<CorrectionValues>({
    resolver: zodResolver(correctionSchema),
    defaultValues: { value: "" },
  });

  return (
    <Dialog
      open={Boolean(item)}
      onOpenChange={(open) => {
        if (!open) {
          form.reset();
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Correct the value</DialogTitle>
          <DialogDescription>
            {item ? `${humanizeParam(item.name)} of ${item.mpn}` : ""}. The corrected value is sent
            to the backend and the status becomes accepted.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => onSubmit(Number(values.value)))}
          className="space-y-4"
        >
          <Field data-invalid={Boolean(form.formState.errors.value)}>
            <FieldLabel htmlFor="correction-value">Correct value</FieldLabel>
            <Input
              id="correction-value"
              inputMode="decimal"
              placeholder={
                item?.value !== null && item?.value !== undefined ? String(item.value) : "0"
              }
              {...form.register("value")}
            />
            <FieldError errors={[form.formState.errors.value]} />
          </Field>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Save the correction</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
