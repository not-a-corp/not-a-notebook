import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";

import { ensureSession } from "@/api/session";
import { AppLayout } from "@/routes/app-layout";
import { AuthPage } from "@/routes/auth/auth-page";
import { Home } from "@/routes/home";
import { Root } from "@/routes/root";

// Routes are declared in code, not generated from the file tree: the route
// table is read here, in one place (design.md §2).
const rootRoute = createRootRoute({ component: Root });

interface AuthSearch {
  error?: string;
}

function validateAuthSearch(search: Record<string, unknown>): AuthSearch {
  const error = search.error;
  if (typeof error !== "string") {
    return {};
  }

  return { error };
}

// Signed in already: the sign-in pages have nothing to offer.
async function leaveIfSignedIn() {
  const signedIn = await ensureSession();
  if (signedIn) {
    throw redirect({ to: "/" });
  }
}

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: validateAuthSearch,
  beforeLoad: leaveIfSignedIn,
  component: function Login() {
    const search = loginRoute.useSearch();
    return <AuthPage mode="sign-in" callbackError={search.error} />;
  },
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  beforeLoad: leaveIfSignedIn,
  component: function Register() {
    return <AuthPage mode="register" callbackError={undefined} />;
  },
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: async () => {
    const signedIn = await ensureSession();
    if (!signedIn) {
      throw redirect({ to: "/login" });
    }
  },
  component: AppLayout,
});

const homeRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: Home,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  registerRoute,
  appRoute.addChildren([homeRoute]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
