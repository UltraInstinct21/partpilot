/**
 * Application-wide constants for PartPilot.
 * Matches backend validation rules and DESIGN.md design system.
 */

// Confidence thresholds matching backend Tier validator and DESIGN.md
// High >= 0.90: trustworthy extraction
// Medium 0.70 - 0.89: usable, minor ambiguity
// Low < 0.70: flagged for human review
export const CONFIDENCE_THRESHOLDS = {
  HIGH: 0.9,
  MEDIUM: 0.7,
} as const;

export type ConfidenceTier = "high" | "medium" | "low" | "unknown";

export function getConfidenceTier(score: number | null | undefined): ConfidenceTier {
  if (score === null || score === undefined || Number.isNaN(score)) return "unknown";
  if (score >= CONFIDENCE_THRESHOLDS.HIGH) return "high";
  if (score >= CONFIDENCE_THRESHOLDS.MEDIUM) return "medium";
  return "low";
}

export function getConfidenceSegments(score: number | null | undefined): number {
  if (score === null || score === undefined || Number.isNaN(score)) return 0;
  if (score >= 0.9) return 4;
  if (score >= 0.75) return 3;
  if (score >= 0.5) return 2;
  if (score > 0) return 1;
  return 0;
}

export type ParameterDirection = "lower" | "higher";

/**
 * Which value is the better one for engineering comparison.
 * A lower Rds(on), lower Qg, or lower propagation delay is better.
 * A higher breakdown voltage, continuous current, or operating temperature is better.
 */
export const PARAMETER_DIRECTION: Record<string, ParameterDirection> = {
  // MOSFET parameters
  rds_on: "lower",
  total_gate_charge_qg: "lower",
  gate_drain_charge_qgd: "lower",
  input_capacitance_ciss: "lower",
  output_capacitance_coss: "lower",
  thermal_resistance: "lower",
  reverse_recovery_qrr: "lower",
  vds_max: "higher",
  id_continuous: "higher",
  vgs_max: "higher",
  vgs_threshold: "higher",
  max_junction_temp: "higher",

  // Gate driver parameters
  propagation_delay: "lower",
  rise_time: "lower",
  fall_time: "lower",
  peak_source_current: "higher",
  peak_sink_current: "higher",
  supply_voltage_max: "higher",
  channel_count: "higher",
  uvlo_threshold: "higher",
};

export const MAX_COMPARE_PARTS = 4;
