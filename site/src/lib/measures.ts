/**
 * The measures the site offers, and what each one answers.
 *
 * Three denominators are defensible and they answer different questions, so all
 * three are offered and the one on screen is always named. The default is the
 * share of positive outcomes, because that is the closest available proxy for
 * the decision point under examination: of the cases where somebody was held to
 * account, how many were dealt with outside court.
 *
 * There is deliberately no composite score and no overall ranking. A rank
 * exists only inside a stated measure.
 */
import { NO_DENOMINATOR_FORCES, oocdSum, value, type Basis, type CountRow, type FraudVariant } from "./data";

export type MeasureId =
  | "share_positive"
  | "share_assigned"
  | "rate_per_1000_recorded_crime"
  | "volume";

export interface Measure {
  id: MeasureId;
  label: string;
  short: string;
  question: string;
  unit: "percentage" | "rate" | "count";
  /** Forces without a meaningful denominator are dropped from this measure. */
  needsDenominator: boolean;
  axisLabel: string;
}

export const MEASURES: Measure[] = [
  {
    id: "share_positive",
    label: "Share of positive outcomes",
    short: "Share of positive outcomes",
    question:
      "Of the cases where somebody was held to account, by a charge or by an out of court disposal, how many were dealt with outside court?",
    unit: "percentage",
    needsDenominator: false,
    axisLabel: "Out of court share of positive outcomes",
  },
  {
    id: "share_assigned",
    label: "Share of all assigned outcomes",
    short: "Share of all outcomes",
    question:
      "Of everything the force closed, including the cases where nobody was held to account, how much ran through an out of court route?",
    unit: "percentage",
    needsDenominator: false,
    axisLabel: "Out of court share of all assigned outcomes",
  },
  {
    id: "rate_per_1000_recorded_crime",
    label: "Rate per 1,000 recorded crimes",
    short: "Per 1,000 recorded crimes",
    question:
      "How many out of court disposals does the force issue for every thousand crimes it records?",
    unit: "rate",
    needsDenominator: true,
    axisLabel: "Out of court disposals per 1,000 recorded crimes",
  },
  {
    id: "volume",
    label: "Absolute volume",
    short: "Volume",
    question: "How many out of court disposals did the force issue?",
    unit: "count",
    needsDenominator: false,
    axisLabel: "Out of court disposals",
  },
];

export const DEFAULT_MEASURE: MeasureId = "share_positive";

export function measureById(id: MeasureId): Measure {
  const measure = MEASURES.find((entry) => entry.id === id);
  if (!measure) throw new Error(`Unknown measure: ${id}`);
  return measure;
}

export interface MeasureOptions {
  basis: Basis;
  variant: FraudVariant;
  types?: readonly number[];
  recordedCrime?: number | null;
  force?: string;
}

/**
 * Compute one measure for one row. Returns null rather than a number when the
 * measure cannot be computed, so a missing denominator never becomes a zero.
 */
export function compute(id: MeasureId, row: CountRow, options: MeasureOptions): number | null {
  const { basis, variant, types, recordedCrime, force } = options;
  const oocd = oocdSum(row, basis, variant, types);

  if (id === "volume") return oocd;

  if (id === "rate_per_1000_recorded_crime") {
    if (force && NO_DENOMINATOR_FORCES.has(force)) return null;
    if (!recordedCrime || recordedCrime <= 0) return null;
    return (oocd / recordedCrime) * 1000;
  }

  // The denominator is fixed and does not follow the disposal subset control.
  // Positive outcomes are charge or summons plus all six out of court types,
  // whichever types are selected, so the shares for the six types add up to the
  // share for all six together. Narrowing the denominator with the numerator
  // would make every subset look larger than it is.
  const denominator =
    id === "share_positive"
      ? value(row, basis, variant, "positive")
      : value(row, basis, variant, "assigned");
  if (!denominator) return null;
  return (oocd / denominator) * 100;
}

export function formatMeasure(id: MeasureId, measureValue: number | null): string {
  if (measureValue === null || Number.isNaN(measureValue)) return "not available";
  const measure = measureById(id);
  if (measure.unit === "percentage") return `${measureValue.toFixed(1)}%`;
  if (measure.unit === "rate") return measureValue.toFixed(1);
  return Math.round(measureValue).toLocaleString("en-GB");
}
