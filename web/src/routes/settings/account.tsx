import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Lock } from "lucide-react";
import { useState, type SubmitEvent } from "react";

import { changePassword, getAccount, type Account, type OAuthProvider } from "@/api/auth";
import { ApiError } from "@/api/errors";
import { signedOut } from "@/api/session";
import { GitHubMark, GoogleMark } from "@/components/brand-marks";
import { toast } from "@/components/toaster";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { providerName, sentenceForError } from "@/lib/words";

import { Group, Row, SectionTitle } from "./settings-ui";

// design.md §2.7 — Account: how you sign in to this instance.
export function AccountSettings() {
  const account = useQuery({ queryKey: ["account"], queryFn: getAccount });

  return (
    <>
      <SectionTitle title="Account" description="How you sign in to this instance." />
      {account.data !== undefined && <AccountGroups account={account.data} />}
    </>
  );
}

function AccountGroups({ account }: { account: Account }) {
  return (
    <>
      <Group label="Sign-in">
        <Row label="Email" help="You sign in with it. It can't be changed here.">
          <span className="flex h-8 w-80 items-center justify-between rounded-md border border-border bg-surface px-3 text-text-muted">
            <span className="truncate">{account.email}</span>
            <Lock className="size-3.5 flex-none" />
          </span>
        </Row>
        <Row label="Password" help="Changing it signs you out on every device, this one included.">
          <PasswordForm hasPassword={account.hasPassword} />
        </Row>
      </Group>
      {account.oauth.length > 0 && (
        <Group label="Linked accounts">
          {account.oauth.map((provider) => (
            <LinkedProvider key={provider} provider={provider} />
          ))}
        </Group>
      )}
    </>
  );
}

// Linking and unlinking are not in the API yet (api.md, What is not here yet):
// the providers are shown as they are.
function LinkedProvider({ provider }: { provider: OAuthProvider }) {
  let mark = <GitHubMark />;
  if (provider === "google") {
    mark = <GoogleMark />;
  }

  return (
    <Row
      label={
        <span className="flex items-center gap-2">
          {mark}
          {providerName(provider)}
        </span>
      }
    >
      <span className="flex h-full items-center text-sm text-text-muted">
        Signed in with {providerName(provider)}
      </span>
    </Row>
  );
}

function PasswordForm({ hasPassword }: { hasPassword: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [currentError, setCurrentError] = useState<string | null>(null);
  const [nextError, setNextError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  let action = "Change password";
  if (!hasPassword) {
    action = "Set password";
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setCurrentError(null);
    setNextError(null);

    // api.md: 8 to 128 characters, nothing else required.
    if (next.length < 8 || next.length > 128) {
      setNextError("8 to 128 characters.");
      return;
    }
    if (hasPassword && current === "") {
      setCurrentError("Enter your current password.");
      return;
    }

    setSaving(true);
    try {
      let currentPassword: string | null = null;
      if (hasPassword) {
        currentPassword = current;
      }
      await changePassword(currentPassword, next);
      // Every session is gone, this one included (api.md): sign in again.
      signedOut();
      queryClient.clear();
      toast("Password changed. Sign in with the new one.");
      await navigate({ to: "/login" });
    } catch (error) {
      if (error instanceof ApiError && error.code === "INVALID_CREDENTIALS") {
        setCurrentError("That isn't the current password.");
      } else {
        toast(sentenceForError(error));
      }
      setSaving(false);
    }
  }

  return (
    <form className="flex w-80 flex-col gap-3" noValidate onSubmit={(event) => void submit(event)}>
      {hasPassword && (
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Current password</span>
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            aria-invalid={currentError !== null}
            onChange={(event) => {
              setCurrent(event.target.value);
            }}
          />
          {currentError !== null && <span className="text-xs text-danger">{currentError}</span>}
        </label>
      )}
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">New password</span>
        <Input
          type="password"
          autoComplete="new-password"
          value={next}
          aria-invalid={nextError !== null}
          onChange={(event) => {
            setNext(event.target.value);
          }}
        />
        {nextError === null && (
          <span className="text-xs text-text-muted">8 to 128 characters.</span>
        )}
        {nextError !== null && <span className="text-xs text-danger">{nextError}</span>}
      </label>
      <Button type="submit" variant="secondary" className="self-start" disabled={saving}>
        {action}
      </Button>
    </form>
  );
}
