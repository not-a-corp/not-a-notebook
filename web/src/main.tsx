import "@/styles/app.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { applyTheme, followSystemTheme, readThemeChoice } from "@/lib/theme";
import { queryClient } from "@/lib/query-client";
import { router } from "@/router";

const root = document.documentElement;
applyTheme(root, readThemeChoice(localStorage));
followSystemTheme(root, localStorage);

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html has no #root element");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
