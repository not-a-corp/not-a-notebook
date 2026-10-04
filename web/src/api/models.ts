import { requestJson } from "./client";
import { asRecord, dataList, nullableString, oneOf, string } from "./decode";

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
