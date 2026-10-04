import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { getAccount, logout } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";

// A stand-in until the shell (sidebar and home composer) replaces it: it shows
// who is signed in and lets them sign out.
export function Home() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const account = useQuery({ queryKey: ["account"], queryFn: getAccount });

  async function signOut() {
    await logout();
    queryClient.clear();
    await navigate({ to: "/login" });
  }

  return (
    <main className="flex h-full flex-col items-center justify-center gap-4 bg-surface">
      <Wordmark />
      <p className="text-sm text-text-muted">{account.data?.email}</p>
      <Button variant="secondary" onClick={() => void signOut()}>
        Sign out
      </Button>
    </main>
  );
}
