import type { Data, Layout } from "plotly.js";
import { useEffect, useRef } from "react";

import { isRecord, type Json } from "@/api/decode";
import { token, useAppliedTheme } from "@/lib/use-theme";

import { themeFigure, type ChartTokens } from "./chart-theme";

// The kernel's figure is plotly.js's own input format; plotly.js validates what
// it is given. These guards only state that a record is what it receives.
function isTrace(value: Json): value is Json & Data {
  return isRecord(value);
}

function isLayout(value: Json): value is Json & Partial<Layout> {
  return isRecord(value);
}

function chartTokens(): ChartTokens {
  const palette: string[] = [];
  for (let index = 1; index <= 8; index += 1) {
    palette.push(token(`chart-${String(index)}`));
  }

  return {
    text: token("text"),
    textMuted: token("text-muted"),
    border: token("border"),
    palette,
  };
}

// The partial bundle with the trace types plotly express emits (design.md §10),
// loaded only when a chart is on screen.
async function loadPlotly() {
  const module = await import("plotly.js/dist/plotly-cartesian.min.js");
  return module.default;
}

// design.md §3.4: the figure, full cell width, with the app's chart theme.
export function PlotlyChart({ spec, label }: { spec: Json; label: string }) {
  const container = useRef<HTMLDivElement>(null);
  const theme = useAppliedTheme();

  useEffect(() => {
    const element = container.current;
    if (element === null) {
      return;
    }

    let cancelled = false;
    void loadPlotly().then((plotly) => {
      if (cancelled) {
        return;
      }
      const figure = themeFigure(spec, chartTokens());
      const data = figure.data.filter(isTrace);
      if (!isLayout(figure.layout)) {
        return;
      }
      void plotly.react(element, data, figure.layout, {
        responsive: true,
        // The mockups draw no toolbar; dragging zooms, a double-click resets.
        displayModeBar: false,
      });
    });

    return () => {
      cancelled = true;
    };
  }, [spec, theme]);

  useEffect(() => {
    const element = container.current;
    return () => {
      if (element !== null) {
        void import("plotly.js/dist/plotly-cartesian.min.js").then((module) => {
          module.default.purge(element);
        });
      }
    };
  }, []);

  return <div ref={container} role="img" aria-label={label} className="w-full" />;
}
