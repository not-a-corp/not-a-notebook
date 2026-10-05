import { describe, expect, it } from "vitest";

import { checkModel, endpointOf, fieldsOf, type ModelDraft } from "./model-form";

const DRAFT: ModelDraft = {
  name: "Local Qwen",
  adapter: "openai_compatible",
  baseUrl: "http://host.docker.internal:11434/v1",
  model: "qwen3:14b",
  dialect: "text",
  key: "",
};

describe("checkModel", () => {
  it("accepts what the API accepts", () => {
    expect(checkModel(DRAFT)).toEqual({});
  });

  it("asks an OpenAI-compatible model for its base URL", () => {
    const missing = Object.assign(structuredClone(DRAFT), { baseUrl: "" });

    expect(checkModel(missing).baseUrl).toBe("An OpenAI-compatible model needs its base URL.");
  });

  it("refuses a base URL that is not http or https", () => {
    const ftp = Object.assign(structuredClone(DRAFT), { baseUrl: "ftp://example.com" });

    expect(checkModel(ftp).baseUrl).toBe("An http or https URL.");
  });
});

describe("fieldsOf", () => {
  it("sends no base URL when none was typed", () => {
    const anthropic = Object.assign(structuredClone(DRAFT), { adapter: "anthropic", baseUrl: " " });

    expect(fieldsOf(anthropic).baseUrl).toBeNull();
  });
});

describe("endpointOf", () => {
  it("shows the endpoint, or the provider's own host", () => {
    expect(endpointOf("openai_compatible", "https://openrouter.ai/api/v1/")).toBe(
      "openrouter.ai/api/v1",
    );
    expect(endpointOf("anthropic", null)).toBe("api.anthropic.com");
  });
});
