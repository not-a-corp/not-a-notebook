import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode, type SubmitEvent } from "react";

import {
  getAuthOptions,
  login,
  oauthStartUrl,
  pendingOAuthProvider,
  register,
  rememberOAuthProvider,
  type OAuthProvider,
} from "@/api/auth";
import { GitHubMark, GoogleMark } from "@/components/brand-marks";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Wordmark } from "@/components/wordmark";
import { cn } from "@/lib/cn";
import { providerName, sentenceFor, sentenceForError } from "@/lib/words";

import { hasErrors, validateCredentials, type FieldErrors } from "./validate";

export type AuthMode = "sign-in" | "register";

interface AuthPageProps {
  mode: AuthMode;
  // `?error=` from an OAuth callback (api.md): a code, turned into a sentence.
  callbackError: string | undefined;
}

// design.md §2.2 — the centred card.
export function AuthPage({ mode, callbackError }: AuthPageProps) {
  const navigate = useNavigate();
  const options = useQuery({ queryKey: ["auth-options"], queryFn: getAuthOptions });

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const registrationOpen = options.data?.registrationOpen ?? false;
  const providers = options.data?.oauth ?? [];

  let title = "Sign in";
  let submitLabel = "Sign in";
  let passwordAutoComplete = "current-password";
  if (mode === "register") {
    title = "Create account";
    submitLabel = "Create account";
    passwordAutoComplete = "new-password";
  }
  if (submitting) {
    submitLabel = "One moment…";
  }

  // With registration closed, the register page is not there (design.md §2.2).
  if (mode === "register" && options.data !== undefined && !registrationOpen) {
    return <Navigate to="/login" replace />;
  }

  let banner = formError;
  if (banner === null && callbackError !== undefined) {
    const provider = pendingOAuthProvider() ?? "your provider";
    banner = sentenceFor(callbackError, "", { provider });
  }

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    const errors = validateCredentials(email, password);
    setFieldErrors(errors);
    if (hasErrors(errors)) {
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      const credentials = { email, password };
      if (mode === "register") {
        await register(credentials);
      } else {
        await login(credentials);
      }
      await navigate({ to: "/" });
    } catch (error) {
      setFormError(sentenceForError(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-full items-center justify-center bg-surface p-4">
      <div className="flex flex-col items-center gap-4">
        <div className="flex w-[400px] flex-col gap-6 rounded-xl border border-border bg-surface-raised p-8">
          <Wordmark />

          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold">{title}</h1>
            <p className="text-text-muted">A data analyst that shows its work.</p>
          </div>

          {banner !== null && (
            <p role="alert" className="text-sm text-danger">
              {banner}
            </p>
          )}

          <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
            <Field label="Email" error={fieldErrors.email}>
              <Input
                type="email"
                name="email"
                autoComplete="email"
                autoFocus
                value={email}
                aria-invalid={fieldErrors.email !== undefined}
                onChange={(event) => {
                  setEmail(event.target.value);
                }}
              />
            </Field>
            <Field label="Password" error={fieldErrors.password}>
              <Input
                type="password"
                name="password"
                autoComplete={passwordAutoComplete}
                value={password}
                aria-invalid={fieldErrors.password !== undefined}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </Field>
            <Button type="submit" className="w-full text-base" disabled={submitting}>
              {submitLabel}
            </Button>
          </form>

          {providers.length > 0 && (
            <>
              <div className="flex items-center gap-3 text-xs text-text-muted">
                <span className="h-px flex-1 bg-border" />
                or
                <span className="h-px flex-1 bg-border" />
              </div>
              <div className="flex flex-col gap-2">
                {providers.map((provider) => (
                  <OAuthButton key={provider} provider={provider} />
                ))}
              </div>
            </>
          )}

          <SwitchMode mode={mode} registrationOpen={registrationOpen} />
        </div>
        <div className="font-mono text-xs text-text-muted">{window.location.host}</div>
      </div>
    </main>
  );
}

interface FieldProps {
  label: string;
  error: string | undefined;
  children: ReactNode;
}

function Field({ label, error, children }: FieldProps) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {error !== undefined && <span className="text-xs text-danger">{error}</span>}
    </label>
  );
}

function OAuthButton({ provider }: { provider: OAuthProvider }) {
  let mark = <GitHubMark />;
  if (provider === "google") {
    mark = <GoogleMark />;
  }

  return (
    <a
      href={oauthStartUrl(provider)}
      onClick={() => {
        rememberOAuthProvider(provider);
      }}
      className={cn(buttonVariants({ variant: "secondary" }), "w-full text-base")}
    >
      {mark}
      Continue with {providerName(provider)}
    </a>
  );
}

function SwitchMode({ mode, registrationOpen }: { mode: AuthMode; registrationOpen: boolean }) {
  if (mode === "register") {
    return (
      <p className="text-center text-sm text-text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-accent">
          Sign in
        </Link>
      </p>
    );
  }

  if (!registrationOpen) {
    return null;
  }

  return (
    <p className="text-center text-sm text-text-muted">
      No account yet?{" "}
      <Link to="/register" className="font-medium text-accent">
        Create one
      </Link>
    </p>
  );
}
