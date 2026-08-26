/**
 * Load the caveats from etl/annotations.yml.
 *
 * That file is the single source of truth. Adding a caveat is a change to it
 * alone: the marker appears on every chart it touches and the full text appears
 * on the methodology page, with no code change.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load as loadYaml } from "js-yaml";

export interface Annotation {
  id: string;
  scope: "national" | string[];
  financial_years: "all" | string[];
  measures: "all" | string[];
  label: string;
  text: string;
  source_url: string;
  source_citation: string;
  source_url_verified: boolean | null;
  /** Set when the note makes a claim not yet reconciled with the data. */
  needs_review?: boolean;
}

interface AnnotationFile {
  version: number;
  last_reviewed: string;
  annotations: Annotation[];
}

const path = join(process.cwd(), "..", "etl", "annotations.yml");
const parsed = loadYaml(readFileSync(path, "utf8")) as AnnotationFile;

export const annotationVersion = parsed.version;
export const annotationsLastReviewed = String(parsed.last_reviewed);
export const annotations: Annotation[] = parsed.annotations;

/** Stable numbering, so footnote 2 means the same thing on every page. */
export const annotationNumber = new Map(annotations.map((entry, index) => [entry.id, index + 1]));

export function appliesToForce(annotation: Annotation, force: string): boolean {
  if (annotation.scope === "national") return true;
  return Array.isArray(annotation.scope) && annotation.scope.includes(force);
}

export function appliesToMeasure(annotation: Annotation, measure: string): boolean {
  if (annotation.measures === "all" || annotation.measures === undefined) return true;
  return Array.isArray(annotation.measures) && annotation.measures.includes(measure);
}

export function forForce(force: string): Annotation[] {
  return annotations.filter((entry) => appliesToForce(entry, force));
}

export function byIds(ids: string[]): Annotation[] {
  return ids.map((id) => {
    const found = annotations.find((entry) => entry.id === id);
    if (!found) throw new Error(`Unknown annotation id: ${id}`);
    return found;
  });
}

/**
 * Outcome 22 recording was voluntary before 2021/22, so charts that show it
 * shade the earlier period. The boundary lives here rather than in each chart.
 */
export const OUTCOME_22_COMPULSORY_FROM = "2021/22";

export function isBeforeOutcome22Compulsory(fy: string): boolean {
  return Number(fy.slice(0, 4)) < Number(OUTCOME_22_COMPULSORY_FROM.slice(0, 4));
}
