import { Navigate, Outlet } from "@tanstack/react-router";

import { useSession } from "@/api/use-session";

// Every signed-in screen sits under this layout. The route's guard handles the
// first load; this handles the session ending later — a refresh that fails, or
// signing out in another place — by going back to sign in.
export function AppLayout() {
  const session = useSession();
  if (session.status === "signed-out") {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
