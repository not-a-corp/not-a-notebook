import { isRecord, type Json } from "@/api/decode";

// design.md §5.4: a chart from the kernel is a Plotly spec, restyled here so it
// always matches the app, in every theme.

export interface ChartTokens {
  text: string;
  textMuted: string;
  border: string;
  palette: string[];
}

// plotly.py's own template, which plotly express also writes into each trace as
// an explicit colour. A colour from this list was never chosen by the code; it
// is replaced, at the same position, by the app's palette — so a figure's
// grouping keeps its order. Any other colour the code set is kept (§5.4).
const PLOTLY_DEFAULT_COLORWAY = [
  "#636efa",
  "#ef553b",
  "#00cc96",
  "#ab63fa",
  "#ffa15a",
  "#19d3f3",
  "#ff6692",
  "#b6e880",
  "#ff97ff",
  "#fecb52",
];

const DEFAULT_HEIGHT = 300;

function themedColor(value: unknown, palette: string[]): unknown {
  if (typeof value !== "string") {
    return value;
  }

  const position = PLOTLY_DEFAULT_COLORWAY.indexOf(value.toLowerCase());
  if (position === -1) {
    return value;
  }

  return palette[position % palette.length] ?? value;
}

function recolor(part: unknown, palette: string[]): void {
  if (!isRecord(part)) {
    return;
  }
  if ("color" in part) {
    part.color = themedColor(part.color, palette);
  }
}

function themeAxis(axis: unknown, tokens: ChartTokens, showGrid: boolean): Json {
  const themed: Json = isRecord(axis) ? axis : {};
  themed.gridcolor = tokens.border;
  themed.linecolor = tokens.textMuted;
  themed.zerolinecolor = tokens.border;
  themed.tickfont = { family: "Inter", size: 12, color: tokens.textMuted };
  themed.showgrid = showGrid;
  // Room for the tick labels and the axis title, measured, never overlapping.
  themed.automargin = true;
  if (isRecord(themed.title)) {
    themed.title.font = { family: "Inter", size: 12, color: tokens.textMuted };
  }
  return themed;
}

function isVerticalBar(trace: Json): boolean {
  return trace.type === "bar" && trace.orientation !== "h";
}

// A copy of the spec, restyled. The kernel's spec is never changed in place:
// the query cache holds it, and a theme change restyles it again from scratch.
export function themeFigure(spec: Json, tokens: ChartTokens): { data: Json[]; layout: Json } {
  const copy = structuredClone(spec);

  const data: Json[] = [];
  if (Array.isArray(copy.data)) {
    for (const trace of copy.data) {
      if (isRecord(trace)) {
        recolor(trace.marker, tokens.palette);
        recolor(trace.line, tokens.palette);
        data.push(trace);
      }
    }
  }

  const layout: Json = isRecord(copy.layout) ? copy.layout : {};
  // The kernel's template is plotly.py's look; the app's look replaces it.
  delete layout.template;

  layout.paper_bgcolor = "rgba(0,0,0,0)";
  layout.plot_bgcolor = "rgba(0,0,0,0)";
  layout.colorway = tokens.palette;
  layout.font = { family: "Inter", size: 12, color: tokens.textMuted };
  layout.barcornerradius = 2;
  layout.margin = { l: 8, r: 16, t: 40, b: 8 };
  if (typeof layout.height !== "number") {
    layout.height = DEFAULT_HEIGHT;
  }

  if (isRecord(layout.title)) {
    layout.title.font = { family: "Inter", size: 13, weight: 500, color: tokens.text };
    layout.title.x = 0;
    layout.title.xref = "paper";
  }

  // Horizontal gridlines only on bar charts (§5.4).
  const bars = data.some(isVerticalBar);
  layout.xaxis = themeAxis(layout.xaxis, tokens, !bars);
  layout.yaxis = themeAxis(layout.yaxis, tokens, true);

  // A legend on top when there is more than one series.
  if (data.length > 1) {
    layout.legend = { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: layout.font };
  }

  return { data, layout };
}
