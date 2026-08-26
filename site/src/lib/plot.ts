/**
 * Render Observable Plot to SVG at build time.
 *
 * Charts are baked into the HTML as SVG. They are visible with JavaScript
 * turned off, they print, and they need no client side data request. The
 * interactive controls on /compare are a progressive enhancement on top of a
 * table that already works without them.
 */
import { JSDOM } from "jsdom";
import * as Plot from "@observablehq/plot";

const dom = new JSDOM("<!DOCTYPE html><body></body>");

export interface RenderOptions {
  /** Accessible title, read out in place of the image. */
  title: string;
  /** Longer description of what the chart shows. */
  description?: string;
}

export function renderPlot(options: Plot.PlotOptions, accessible: RenderOptions): string {
  const figure = Plot.plot({
    ...options,
    document: dom.window.document,
    style: { background: "transparent", overflow: "visible", ...(options.style as object) },
  }) as unknown as Element;

  const svg = figure.tagName.toLowerCase() === "svg" ? figure : figure.querySelector("svg");
  if (!svg) return figure.outerHTML;

  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", accessible.title);
  if (accessible.description) {
    const desc = dom.window.document.createElementNS("http://www.w3.org/2000/svg", "desc");
    desc.textContent = accessible.description;
    svg.insertBefore(desc, svg.firstChild);
  }
  // Plot labels each mark group with aria-label. A plain g element has no
  // implicit role, so aria-label on it is prohibited and axe reports it as a
  // serious violation. The root already carries role="img" and the accessible
  // name, and the numbers are in the table beside every chart, so the interior
  // is hidden from assistive technology rather than relabelled.
  for (const group of Array.from(svg.querySelectorAll("g[aria-label]"))) {
    group.removeAttribute("aria-label");
  }
  for (const child of Array.from(svg.children)) {
    if (child.tagName.toLowerCase() !== "desc") child.setAttribute("aria-hidden", "true");
  }
  svg.removeAttribute("aria-hidden");
  return figure.outerHTML;
}

/** Shared axis and grid styling, kept recessive so the marks carry the chart. */
export const PLOT_BASE = {
  marginLeft: 56,
  marginBottom: 40,
  marginTop: 16,
  marginRight: 16,
  style: { fontSize: "12px", fontFamily: "inherit" },
} as const;
