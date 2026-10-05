import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";

import { ensureSession } from "@/api/session";
import { AppLayout } from "@/routes/app-layout";
import { AuthPage } from "@/routes/auth/auth-page";
import { ConversationScreen } from "@/routes/conversation/conversation-screen";
import { Home } from "@/routes/home/home";
import { Root } from "@/routes/root";
import { GeneralSettings } from "@/routes/settings/general";
import { SettingsLayout } from "@/routes/settings/settings-layout";

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

const conversationRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/c/$conversationId",
  component: function Conversation() {
    const { conversationId } = conversationRoute.useParams();
    // Keyed by id, so moving between conversations starts each screen fresh.
    return <ConversationScreen key={conversationId} conversationId={conversationId} />;
  },
});

// design.md §2.6: each section has its own route, so it can be linked to.
const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings",
  component: SettingsLayout,
});

const settingsIndexRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/settings/general" });
  },
});

const generalRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "/general",
  component: GeneralSettings,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  registerRoute,
  appRoute.addChildren([
    homeRoute,
    conversationRoute,
    settingsRoute.addChildren([settingsIndexRoute, generalRoute]),
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
