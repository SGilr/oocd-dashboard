/**
 * The categorical palette for the six disposal types, and the textures that
 * carry the same identity when colour is not available.
 *
 * The hues were validated for colour vision deficiency separation, chroma and
 * lightness band against both the light and the dark chart surface. Three of
 * the light steps sit below 3:1 contrast against the light surface, so every
 * chart that uses them also carries a legend, direct labels where they fit, and
 * a data table, rather than relying on colour alone.
 *
 * Greyscale is handled by texture, not by lightness. Six hues cannot be spread
 * across six distinguishable greys and still stay inside the lightness band the
 * palette needs, so each disposal type carries a distinct SVG pattern as well
 * as a hue. Printed in greyscale, or read by anyone who cannot separate the
 * hues, the pattern is what tells the series apart.
 */
export interface SeriesStyle {
  type: number;
  label: string;
  short: string;
  light: string;
  dark: string;
  /** Pattern id, defined once per page by TexturePatterns.astro. */
  texture: string;
}

export const DISPOSAL_SERIES: SeriesStyle[] = [
  {
    type: 8,
    label: "Community resolution",
    short: "Community resolution",
    light: "#2a78d6",
    dark: "#3987e5",
    texture: "solid",
  },
  {
    type: 22,
    label: "Outcome 22, diversionary, educational or intervention activity",
    short: "Outcome 22",
    light: "#eb6834",
    dark: "#d95926",
    texture: "diagonal-right",
  },
  {
    type: 3,
    label: "Caution, adults",
    short: "Caution, adults",
    light: "#1baf7a",
    dark: "#199e70",
    texture: "diagonal-left",
  },
  {
    type: 2,
    label: "Caution, youths",
    short: "Caution, youths",
    light: "#eda100",
    dark: "#c98500",
    texture: "dots",
  },
  {
    type: 6,
    label: "Penalty notice for disorder",
    short: "Penalty notice",
    light: "#e87ba4",
    dark: "#d55181",
    texture: "horizontal",
  },
  {
    type: 7,
    label: "Cannabis or khat warning",
    short: "Cannabis warning",
    light: "#008300",
    dark: "#008300",
    texture: "grid",
  },
];

/** The charge comparator is drawn in ink, not in a series hue. */
export const CHARGE_STYLE = {
  type: 1,
  label: "Charge or summons",
  short: "Charge or summons",
  light: "#52514e",
  dark: "#c3c2b7",
  texture: "vertical",
};

export const seriesByType = new Map(DISPOSAL_SERIES.map((series) => [series.type, series]));

export function lightColours(): string[] {
  return DISPOSAL_SERIES.map((series) => series.light);
}

export function labels(): string[] {
  return DISPOSAL_SERIES.map((series) => series.short);
}
