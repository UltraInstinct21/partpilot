import { useState } from "react";
import { Plus, X, Pencil, Trash2 } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import type { ParameterConstraint, SearchFilter } from "@/api/hooks";
import { AnimatedList } from "@/components/react-bits/AnimatedList";
import {
  CONSTRAINT_OPERATORS,
  FIELD_META,
  type FilterChip,
  filterToChips,
  removeChip,
  updateConstraintChip,
  updateFieldChip,
  parseNumber,
} from "@/lib/filters";
import { cn } from "@/lib/utils";

export interface FilterChipsProps {
  filter: SearchFilter | undefined;
  explanation?: string | null;
  onChange: (filter: SearchFilter) => void;
  surface?: "haze" | "dark";
  className?: string;
}

const AVAILABLE_FIELDS = [
  { field: "vds_max", label: "Breakdown Voltage (Vds)", unit: "V" },
  { field: "id_continuous", label: "Drain Current (Id)", unit: "A" },
  { field: "rds_on", label: "On-Resistance (Rds_on)", unit: "Ω" },
  { field: "total_gate_charge_qg", label: "Gate Charge (Qg)", unit: "C" },
  { field: "propagation_delay", label: "Propagation Delay (tpd)", unit: "s" },
  { field: "supply_voltage_max", label: "Supply Voltage Max", unit: "V" },
];

function chipLabel(chip: FilterChip): string {
  if (chip.kind === "constraint") return chip.field;
  return FIELD_META[chip.field]?.label ?? chip.field;
}

/**
 * "Understood as" filter chip rail.
 * Pill toggles (9999px radius):
 * - On Haze: 10% black fill with Ink text
 * - On Dark: Ghost outline with white text
 * Popover on click to edit operator/value or remove.
 * Includes "Add filter" field picker and server explanation note.
 */
export function FilterChips({
  filter,
  explanation,
  onChange,
  surface = "dark",
  className,
}: FilterChipsProps) {
  const chips = filterToChips(filter);
  const [editingChip, setEditingChip] = useState<FilterChip | null>(null);
  const [newFieldOpen, setNewFieldOpen] = useState(false);

  const [editOperator, setEditOperator] = useState<string>("");
  const [editValue, setEditValue] = useState<string>("");

  if (!filter) return null;

  const isDark = surface === "dark";

  const handleOpenEdit = (chip: FilterChip) => {
    setEditingChip(chip);
    setEditOperator(chip.operator);
    setEditValue(chip.value);
  };

  const handleSaveEdit = () => {
    if (!editingChip || !filter) return;
    if (editingChip.kind === "field") {
      onChange(updateFieldChip(filter, editingChip, editValue));
    } else {
      const num = parseNumber(editValue);
      const existingConstraint = editingChip.constraint ?? { name: editingChip.field };
      const updatedConstraint: ParameterConstraint = {
        ...existingConstraint,
        name: editingChip.field,
        operator: editOperator as ParameterConstraint["operator"],
        ...(editOperator === "gt" || editOperator === "gte" ? { min: num ?? undefined } : {}),
        ...(editOperator === "lt" || editOperator === "lte" ? { max: num ?? undefined } : {}),
        ...(editOperator === "eq" ? { typ: num ?? undefined } : {}),
      };
      onChange(updateConstraintChip(filter, editingChip, updatedConstraint));
    }
    setEditingChip(null);
  };

  const handleRemove = (chip: FilterChip) => {
    if (!filter) return;
    onChange(removeChip(filter, chip));
    if (editingChip?.id === chip.id) {
      setEditingChip(null);
    }
  };

  const handleAddConstraint = (field: string, unit: string) => {
    const existing = filter.parameters ?? [];
    const updated: ParameterConstraint[] = [
      ...existing,
      { name: field, unit, operator: "lte", max: 10 },
    ];
    onChange({ ...filter, parameters: updated });
    setNewFieldOpen(false);
  };

  return (
    <div className={cn("flex flex-col gap-2", className)} data-testid="filter-chips">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "text-[11px] font-mono uppercase tracking-wider",
            isDark ? "text-zinc-400" : "text-zinc-500",
          )}
        >
          Understood as:
        </span>

        {chips.length === 0 && (
          <span className={cn("text-xs font-mono", isDark ? "text-zinc-400" : "text-zinc-500")}>
            No active constraints
          </span>
        )}

        {chips.map((chip) => {
          const isSelected = editingChip?.id === chip.id;
          const label = chipLabel(chip);

          return (
            <Popover.Root
              key={chip.id}
              open={isSelected}
              onOpenChange={(open) => {
                if (open) handleOpenEdit(chip);
                else setEditingChip(null);
              }}
            >
              <div
                data-chip={chip.field}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs select-none transition-none",
                  isDark
                    ? "border border-white/20 bg-transparent text-white"
                    : "bg-black/10 text-ink",
                )}
              >
                <span className="font-medium">{label}</span>
                <span className="font-mono text-[11px] opacity-70">{chip.operator}</span>
                <span className="font-mono text-[11px]">{chip.value}</span>

                <Popover.Trigger asChild>
                  <button
                    type="button"
                    aria-label={`Edit ${label}`}
                    onClick={() => handleOpenEdit(chip)}
                    className="ml-1 rounded-full p-0.5 hover:bg-black/20 focus-visible:outline-2 focus-visible:outline-white"
                  >
                    <Pencil className="size-3" />
                  </button>
                </Popover.Trigger>

                <button
                  type="button"
                  onClick={() => handleRemove(chip)}
                  aria-label={`Remove ${label}`}
                  className="rounded-full p-0.5 hover:bg-black/20 focus-visible:outline-2 focus-visible:outline-white"
                >
                  <X className="size-3" />
                </button>
              </div>

              <Popover.Portal>
                <Popover.Content
                  align="start"
                  sideOffset={6}
                  className="z-50 w-72 rounded-[12px] border border-white/15 bg-[#18181c] p-4 text-white shadow-none"
                >
                  <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-3">
                    <span className="font-mono text-xs font-semibold uppercase">{label}</span>
                    <button
                      type="button"
                      onClick={() => handleRemove(chip)}
                      className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-white"
                    >
                      <Trash2 className="size-3" />
                      Remove
                    </button>
                  </div>

                  <div className="space-y-3 text-xs">
                    {chip.kind === "constraint" && (
                      <div>
                        <label
                          htmlFor={`op-${chip.id}`}
                          className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1"
                        >
                          Operator
                        </label>
                        <select
                          id={`op-${chip.id}`}
                          value={editOperator}
                          onChange={(e) => setEditOperator(e.target.value)}
                          className="w-full rounded-[4px] border border-white/20 bg-black/50 p-2 font-mono text-xs text-white outline-none focus:border-white/40"
                        >
                          {CONSTRAINT_OPERATORS.map((op) => (
                            <option key={op} value={op} className="bg-[#18181c] text-white">
                              {op}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div>
                      <label
                        htmlFor={`val-${chip.id}`}
                        className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-1"
                      >
                        {label}
                      </label>
                      <input
                        id={`val-${chip.id}`}
                        aria-label={label}
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="w-full rounded-[4px] border border-white/20 bg-black/50 p-2 font-mono text-xs text-white outline-none focus:border-white/40"
                      />
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setEditingChip(null)}
                        className="rounded-[8px] border border-white/20 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={handleSaveEdit}
                        className="rounded-[8px] border border-white bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200"
                      >
                        Apply
                      </button>
                    </div>
                  </div>
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
          );
        })}

        {/* Add Filter Button */}
        <Popover.Root open={newFieldOpen} onOpenChange={setNewFieldOpen}>
          <Popover.Trigger asChild>
            <button
              type="button"
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-none",
                isDark
                  ? "border border-dashed border-white/20 bg-transparent text-zinc-400 hover:text-white hover:border-white/40"
                  : "border border-dashed border-ink/30 bg-transparent text-zinc-600 hover:text-black",
              )}
            >
              <Plus className="size-3" />
              Add filter
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              align="start"
              sideOffset={6}
              className="z-50 w-72 rounded-[12px] border border-white/15 bg-[#18181c] p-2 text-white shadow-none"
            >
              <div className="px-2 py-1 text-[11px] font-mono uppercase font-bold text-zinc-400 border-b border-white/10 mb-1">
                Select Parameter
              </div>
              <AnimatedList
                items={AVAILABLE_FIELDS.map((f) => ({
                  id: f.field,
                  title: f.label,
                  description: `Default limit (Unit: ${f.unit})`,
                  meta: f.unit,
                }))}
                onItemSelect={(item) => {
                  const id = (item as any).id;
                  const found = AVAILABLE_FIELDS.find((f) => f.field === id);
                  if (found) handleAddConstraint(found.field, found.unit);
                }}
                animation="pop"
                theme="dark"
                width="100%"
                maxHeight={220}
                frame={false}
              />
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>

      {/* Server Explanation Note */}
      {explanation && (
        <p
          className={cn(
            "text-xs font-mono",
            isDark ? "text-zinc-400" : "text-zinc-600",
          )}
        >
          {explanation}
        </p>
      )}
    </div>
  );
}
