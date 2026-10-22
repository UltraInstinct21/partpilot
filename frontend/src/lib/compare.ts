export type ParameterDirection = "lower" | "higher";

/**
 * Which value is the better one.
 *
 * A lower Rds(on), a lower gate charge or a lower propagation delay is
 * better; a higher voltage rating or a higher current rating is better.
 * A parameter that is not listed is neutral and is never highlighted.
 */
export const PARAMETER_DIRECTION: Record<string, ParameterDirection> = {
  rds_on: "lower",
  total_gate_charge_qg: "lower",
  gate_drain_charge_qgd: "lower",
  input_capacitance_ciss: "lower",
  output_capacitance_coss: "lower",
  thermal_resistance: "lower",
  propagation_delay: "lower",
  rise_time: "lower",
  fall_time: "lower",
  reverse_recovery_qrr: "lower",
  vds_max: "higher",
  id_continuous: "higher",
  vgs_max: "higher",
  vgs_threshold: "higher",
  peak_source_current: "higher",
  peak_sink_current: "higher",
  supply_voltage_max: "higher",
  uvlo_threshold: "higher",
};

/** The best value of a row, or null when the row is not comparable. */
export function bestValue(name: string, values: Array<number | null | undefined>): number | null {
  const direction = PARAMETER_DIRECTION[name];
  if (!direction) return null;
  const numbers = values.filter(
    (value): value is number => typeof value === "number" && !Number.isNaN(value),
  );
  if (numbers.length === 0) return null;
  return direction === "lower" ? Math.min(...numbers) : Math.max(...numbers);
}
