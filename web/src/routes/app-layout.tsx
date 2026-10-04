import { Navigate, Outlet } from "@tanstack/react-router";

import { useSession } from "@/api/use-session";
import { Sidebar } from "@/components/sidebar/sidebar";

// Every signed-in screen: the sidebar, and the screen beside it. The route's
// guard handles the first load; this handles the session ending later — a
// refresh that fails, or signing out elsewhere — by going back to sign in.
export function AppLayout() {
  const session = useSession();
  if (session.status === "signed-out") {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <Sidebar />
      <main className="flex min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
