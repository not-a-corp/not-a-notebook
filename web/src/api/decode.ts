// Data from the network is `unknown` until it is checked (CLAUDE.md). These are
// the checks: each reads one field, proves its type, and names the field when
// it is wrong — so a contract drift fails loudly at the edge, never deep inside
// a component.

export type Json = Record<string, unknown>;

export class ShapeError extends Error {
  override name = "ShapeError";
}

export function isRecord(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown, what: string): Json {
  if (!isRecord(value)) {
    throw new ShapeError(`${what} is not an object`);
  }

  return value;
}

export function string(json: Json, key: string): string {
  const value = json[key];
  if (typeof value !== "string") {
    throw new ShapeError(`"${key}" is not a string`);
  }

  return value;
}

export function nullableString(json: Json, key: string): string | null {
  const value = json[key];
  if (value === null) {
    return null;
  }

  return string(json, key);
}

export function number(json: Json, key: string): number {
  const value = json[key];
  if (typeof value !== "number") {
    throw new ShapeError(`"${key}" is not a number`);
  }

  return value;
}

export function nullableNumber(json: Json, key: string): number | null {
  const value = json[key];
  if (value === null) {
    return null;
  }

  return number(json, key);
}

export function boolean(json: Json, key: string): boolean {
  const value = json[key];
  if (typeof value !== "boolean") {
    throw new ShapeError(`"${key}" is not a boolean`);
  }

  return value;
}

export function oneOf<T extends string>(json: Json, key: string, allowed: readonly T[]): T {
  const value = json[key];
  const match = allowed.find((candidate) => candidate === value);
  if (match === undefined) {
    throw new ShapeError(`"${key}" is not one of ${allowed.join(", ")}`);
  }

  return match;
}

export function nullableOneOf<T extends string>(
  json: Json,
  key: string,
  allowed: readonly T[],
): T | null {
  const value = json[key];
  if (value === null) {
    return null;
  }

  return oneOf(json, key, allowed);
}

export function array<T>(json: Json, key: string, decodeItem: (item: unknown) => T): T[] {
  const value = json[key];
  if (!Array.isArray(value)) {
    throw new ShapeError(`"${key}" is not a list`);
  }

  return value.map(decodeItem);
}

export function record(json: Json, key: string): Json {
  return asRecord(json[key], `"${key}"`);
}

// A list endpoint answers {"data": [...]} (api.md): the array is read from there.
export function dataList<T>(value: unknown, decodeItem: (item: unknown) => T): T[] {
  const json = asRecord(value, "the response");
  return array(json, "data", decodeItem);
}
