import { request, requestJson } from "./client";
import { asRecord, boolean, dataList, nullableString, number, oneOf, string } from "./decode";

// api.md, Models.

export const ADAPTERS = ["anthropic", "openai_responses", "openai_compatible"] as const;
export type Adapter = (typeof ADAPTERS)[number];

export const DIALECTS = ["tools", "text"] as const;
export type Dialect = (typeof DIALECTS)[number];

export type ModelSource = "environment" | "user";

export interface Model {
  id: string;
  name: string;
  source: ModelSource;
  adapter: Adapter;
  baseUrl: string | null;
  model: string;
  dialect: Dialect;
  keyHint: string | null;
}

export function decodeModel(value: unknown): Model {
  const json = asRecord(value, "model");

  return {
    id: string(json, "id"),
    name: string(json, "name"),
    source: oneOf(json, "source", ["environment", "user"]),
    adapter: oneOf(json, "adapter", ADAPTERS),
    baseUrl: nullableString(json, "base_url"),
    model: string(json, "model"),
    dialect: oneOf(json, "dialect", DIALECTS),
    keyHint: nullableString(json, "key_hint"),
  };
}

export async function listModels(): Promise<Model[]> {
  return dataList(await requestJson("/models"), decodeModel);
}

export interface ModelFields {
  name: string;
  adapter: Adapter;
  baseUrl: string | null;
  model: string;
  dialect: Dialect;
}

export async function createModel(fields: ModelFields, apiKey: string | null): Promise<Model> {
  const created = await requestJson("/models", {
    method: "POST",
    json: {
      name: fields.name,
      adapter: fields.adapter,
      base_url: fields.baseUrl,
      model: fields.model,
      dialect: fields.dialect,
      api_key: apiKey,
    },
  });
  return decodeModel(created);
}

// What happens to the stored key on an edit: kept (not sent), replaced, or
// removed (`api_key: null`) — api.md, PATCH /models/{id}.
export type KeyChange = { kind: "keep" } | { kind: "replace"; key: string } | { kind: "remove" };

export async function updateModel(id: string, fields: ModelFields, key: KeyChange): Promise<Model> {
  const body: Record<string, unknown> = {
    name: fields.name,
    adapter: fields.adapter,
    base_url: fields.baseUrl,
    model: fields.model,
    dialect: fields.dialect,
  };
  if (key.kind === "replace") {
    body.api_key = key.key;
  }
  if (key.kind === "remove") {
    body.api_key = null;
  }
  return decodeModel(await requestJson(`/models/${id}`, { method: "PATCH", json: body }));
}

export async function deleteModel(id: string): Promise<void> {
  await request(`/models/${id}`, { method: "DELETE" });
}

export interface ModelTestResult {
  ok: boolean;
  latencyMs: number;
  error: string | null;
}

// 200 whether or not the model passed: the test ran, and this is its result.
export async function testModel(id: string): Promise<ModelTestResult> {
  const json = asRecord(await requestJson(`/models/${id}/test`, { method: "POST" }), "test");
  return {
    ok: boolean(json, "ok"),
    latencyMs: number(json, "latency_ms"),
    error: nullableString(json, "error"),
  };
}
