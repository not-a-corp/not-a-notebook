import type { Adapter, Dialect, ModelFields } from "@/api/models";

// The form's fields, as typed. Checked here the way the API checks them
// (domain/model_configs.py), so a mistake is named on its field — the API's
// 422 names none.
export interface ModelDraft {
  name: string;
  adapter: Adapter;
  baseUrl: string;
  model: string;
  dialect: Dialect;
  key: string;
}

export interface ModelErrors {
  name?: string;
  baseUrl?: string;
  model?: string;
}

function isHttpUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return (url.protocol === "http:" || url.protocol === "https:") && url.host !== "";
  } catch {
    return false;
  }
}

export function checkModel(draft: ModelDraft): ModelErrors {
  const errors: ModelErrors = {};
  const name = draft.name.trim();
  const baseUrl = draft.baseUrl.trim();

  if (name === "" || name.length > 100) {
    errors.name = "A name, up to 100 characters.";
  }
  if (draft.model.trim() === "") {
    errors.model = "The model's name at the provider.";
  }
  if (baseUrl === "" && draft.adapter === "openai_compatible") {
    errors.baseUrl = "An OpenAI-compatible model needs its base URL.";
  }
  if (baseUrl !== "" && !isHttpUrl(baseUrl)) {
    errors.baseUrl = "An http or https URL.";
  }
  return errors;
}

export function hasModelErrors(errors: ModelErrors): boolean {
  return errors.name !== undefined || errors.baseUrl !== undefined || errors.model !== undefined;
}

export function fieldsOf(draft: ModelDraft): ModelFields {
  const baseUrl = draft.baseUrl.trim();
  let sentUrl: string | null = null;
  if (baseUrl !== "") {
    sentUrl = baseUrl;
  }
  return {
    name: draft.name.trim(),
    adapter: draft.adapter,
    baseUrl: sentUrl,
    model: draft.model.trim(),
    dialect: draft.dialect,
  };
}

// Where a model's requests go, as the table shows it: the endpoint's host and
// path, or the provider's own host when no base URL is set.
export function endpointOf(adapter: Adapter, baseUrl: string | null): string {
  if (baseUrl !== null) {
    return baseUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
  if (adapter === "anthropic") {
    return "api.anthropic.com";
  }
  return "api.openai.com";
}
