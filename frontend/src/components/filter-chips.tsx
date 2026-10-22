import { useEffect, useState } from "react";
import { Pencil, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ParameterConstraint, SearchFilter } from "@/api/hooks";
import {
  CONSTRAINT_OPERATORS,
  FIELD_META,
  type FilterChip,
  filterToChips,
  parseNumber,
  removeChip,
  updateConstraintChip,
  updateFieldChip,
} from "@/lib/filters";

const BOOLEAN_OPTIONS = ["true", "false"];

function chipLabel(chip: FilterChip): string {
  if (chip.kind === "constraint") return chip.field;
  return FIELD_META[chip.field]?.label ?? chip.field;
}

/** The editable chips of the search filter. */
export function FilterChips({
  filter,
  onChange,
}: {
  filter: SearchFilter | undefined;
  onChange: (filter: SearchFilter) => void;
}) {
  const chips = filterToChips(filter);
  const [editing, setEditing] = useState<FilterChip | null>(null);

  if (!filter) return null;

  return (
    <div className="flex flex-col gap-2" data-testid="filter-chips">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Filter
        </span>
        {chips.length === 0 && (
          <span className="text-sm text-muted-foreground">No filter constraint yet.</span>
        )}
        {chips.map((chip) => (
          <Badge
            key={chip.id}
            variant="secondary"
            data-chip={chip.field}
            className="h-7 gap-1.5 rounded-full pr-1 pl-2.5"
          >
            <span className="font-medium">{chipLabel(chip)}</span>
            <span className="font-mono text-[11px] opacity-70">{chip.operator}</span>
            <span className="font-mono text-[11px]">{chip.value}</span>
            <button
              type="button"
              aria-label={`Edit ${chipLabel(chip)}`}
              className="rounded-full p-0.5 hover:bg-background/60"
              onClick={() => setEditing(chip)}
            >
              <Pencil className="size-3" />
            </button>
            <button
              type="button"
              aria-label={`Remove ${chipLabel(chip)}`}
              className="rounded-full p-0.5 hover:bg-background/60"
              onClick={() => onChange(removeChip(filter, chip))}
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
      </div>

      <ChipEditor
        chip={editing}
        filter={filter}
        onClose={() => setEditing(null)}
        onSave={(next) => {
          onChange(next);
          setEditing(null);
        }}
      />
    </div>
  );
}

function ChipEditor({
  chip,
  filter,
  onClose,
  onSave,
}: {
  chip: FilterChip | null;
  filter: SearchFilter;
  onClose: () => void;
  onSave: (filter: SearchFilter) => void;
}) {
  const [value, setValue] = useState("");
  const [operator, setOperator] = useState<ParameterConstraint["operator"]>("lte");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");
  const [typ, setTyp] = useState("");
  const [unit, setUnit] = useState("");

  useEffect(() => {
    if (!chip) return;
    setValue(chip.kind === "field" ? chip.value : "");
    setOperator(chip.constraint?.operator ?? "lte");
    setMin(
      chip.constraint?.min === null || chip.constraint?.min === undefined
        ? ""
        : String(chip.constraint.min),
    );
    setMax(
      chip.constraint?.max === null || chip.constraint?.max === undefined
        ? ""
        : String(chip.constraint.max),
    );
    setTyp(
      chip.constraint?.typ === null || chip.constraint?.typ === undefined
        ? ""
        : String(chip.constraint.typ),
    );
    setUnit(chip.constraint?.unit ?? "");
  }, [chip]);

  if (!chip) return null;

  const isBoolean = chip.field === "in_stock";

  const handleSave = () => {
    if (chip.kind === "field") {
      onSave(updateFieldChip(filter, chip, value));
      return;
    }
    const constraint: ParameterConstraint = {
      name: chip.field,
      operator,
      unit: unit || null,
      min: parseNumber(min),
      max: parseNumber(max),
      typ: parseNumber(typ),
    };
    onSave(updateConstraintChip(filter, chip, constraint));
  };

  return (
    <Dialog open={Boolean(chip)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit filter</DialogTitle>
          <DialogDescription>
            {chipLabel(chip)} {chip.operator}. The search is repeated with the edited filter, the
            language model is not called again.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3">
          {chip.kind === "field" ? (
            <div className="grid gap-1.5">
              <Label htmlFor="chip-value">{chipLabel(chip)}</Label>
              {isBoolean ? (
                <Select value={value} onValueChange={setValue}>
                  <SelectTrigger id="chip-value">
                    <SelectValue placeholder="true or false" />
                  </SelectTrigger>
                  <SelectContent>
                    {BOOLEAN_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id="chip-value"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                />
              )}
            </div>
          ) : (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="chip-operator">Operator</Label>
                <Select
                  value={operator}
                  onValueChange={(next) => setOperator(next as ParameterConstraint["operator"])}
                >
                  <SelectTrigger id="chip-operator">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CONSTRAINT_OPERATORS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1.5">
                  <Label htmlFor="chip-min">Min</Label>
                  <Input id="chip-min" value={min} onChange={(e) => setMin(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="chip-max">Max</Label>
                  <Input id="chip-max" value={max} onChange={(e) => setMax(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="chip-typ">Typical</Label>
                  <Input id="chip-typ" value={typ} onChange={(e) => setTyp(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="chip-unit">Unit</Label>
                  <Input id="chip-unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
                </div>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Apply</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
