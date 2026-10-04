import { ApiError } from "@/api/errors";

// design.md §6: every error code the person can meet, as the sentence they read.
// Short, plain, no blame. `message` from the API is shown only where §6 says so.

export interface WordsContext {
  provider?: string;
  name?: string;
}

const PROVIDER_NAMES: Record<string, string> = {
  google: "Google",
  github: "GitHub",
};

export function providerName(provider: string): string {
  return PROVIDER_NAMES[provider] ?? provider;
}

export function sentenceFor(code: string, message: string, context: WordsContext = {}): string {
  const provider = providerName(context.provider ?? "your provider");

  switch (code) {
    case "INVALID_CREDENTIALS":
      return "Wrong email or password.";
    case "REGISTRATION_CLOSED":
      return "This instance isn't accepting new accounts.";
    case "EMAIL_ALREADY_REGISTERED":
      return "That email already has an account. Sign in with its password.";
    case "OAUTH_FAILED":
      return `Signing in with ${provider} didn't complete. Try again.`;
    case "OAUTH_PROVIDER_NOT_ENABLED":
      return `Signing in with ${provider} isn't enabled on this instance.`;
    case "NO_MODEL_SELECTED":
      return "Pick a model for this conversation first.";
    case "CONVERSATION_BUSY":
      return "Something is already running here. Wait for it, or stop it.";
    case "FILE_ALREADY_EXISTS":
      return `There's already a file named ${context.name ?? "that"} here.`;
    case "FILE_TOO_LARGE":
      return "That file is over this instance's limit.";
    case "UNSUPPORTED_FILE_TYPE":
      return "Only CSV, TSV, Excel and Parquet files can be added.";
    case "MODEL_UNAVAILABLE":
      return `The model's provider failed: ${message}`;
    case "MODEL_REFUSED":
      return "The model declined to answer this.";
    case "STEP_LIMIT":
      return "The analyst kept running code without reaching an answer, and was stopped.";
    case "SANDBOX_UNAVAILABLE":
      return "The kernel couldn't start. Try again in a moment.";
    case "MODEL_MANAGED_BY_ENVIRONMENT":
      return "This model is set in the server's environment and can't be changed here.";
    case "VALIDATION_ERROR":
      // The API names no field (api.md: a 422 never repeats the input), so the
      // forms check their fields first and this is what is left.
      return "Something in the form isn't valid. Check it and try again.";
    default:
      if (code.endsWith("_NOT_FOUND")) {
        return "This doesn't exist, or isn't yours.";
      }

      return "Something went wrong on our side.";
  }
}

export function sentenceForError(error: unknown, context: WordsContext = {}): string {
  if (!(error instanceof ApiError)) {
    return "The server couldn't be reached. Check the connection and try again.";
  }

  const sentence = sentenceFor(error.code, error.message, context);
  if (error.code === "INTERNAL_ERROR" && error.requestId !== null) {
    return `${sentence} Reference: ${error.requestId}.`;
  }

  return sentence;
}
