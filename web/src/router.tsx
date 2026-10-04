import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";

import { Home } from "@/routes/home";
import { Root } from "@/routes/root";

// Routes are declared in code, not generated from the file tree: the route
// table is read here, in one place (design.md §2).
const rootRoute = createRootRoute({ component: Root });

const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Home,
});

const routeTree = rootRoute.addChildren([homeRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
