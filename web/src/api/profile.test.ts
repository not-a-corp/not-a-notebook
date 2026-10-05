import { describe, expect, it } from "vitest";

import { allFindings, readProfile } from "./profile";

// The shape api.md documents, findings at the file and at a table.
const PROFILE = {
  format: "excel",
  readable: true,
  encoding: null,
  sheets: ["Capa", "Vendas"],
  findings: [{ kind: "data_not_on_first_sheet", message: "…", first: "Capa", largest: "Vendas" }],
  tables: [
    {
      sheet: "Vendas",
      rows: 1286,
      column_count: 6,
      columns: [{ name: "região", dtype: "str", missing: 0, distinct: 3, samples: ["Sudeste"] }],
      findings: [
        { kind: "subtotal_rows", message: "…", rows: [4], count: 1 },
        { kind: "inconsistent_labels", message: "…", column: "região", variants: [] },
        { kind: "something_new", message: "a kind this client does not know yet" },
      ],
    },
  ],
};

describe("readProfile", () => {
  it("lists the file's findings first, then each table's, with where they sit", () => {
    const findings = allFindings(readProfile(PROFILE));

    expect(findings.map((finding) => [finding.kind, finding.where])).toEqual([
      ["data_not_on_first_sheet", "file"],
      ["subtotal_rows", "table"],
      ["inconsistent_labels", "região"],
      ["something_new", "table"],
    ]);
    expect(findings[1]?.rows).toEqual([4]);
  });

  it("reads an unreadable file as one, with its error", () => {
    const profile = readProfile({ format: "parquet", readable: false, error: "not Parquet" });

    expect(profile).toMatchObject({ readable: false, error: "not Parquet", tables: [] });
  });
});
