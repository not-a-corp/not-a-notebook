import { describe, expect, it } from "vitest";

import { validateCredentials } from "./validate";

describe("validateCredentials", () => {
  it("accepts what api.md accepts", () => {
    expect(validateCredentials("rafael@example.com", "eight ch")).toEqual({});
  });

  it("names the field that is wrong", () => {
    expect(validateCredentials("rafael", "short")).toEqual({
      email: "Enter an email address.",
      password: "At least 8 characters.",
    });
  });

  it("refuses a password over 128 characters", () => {
    expect(validateCredentials("rafael@example.com", "x".repeat(129)).password).toBe(
      "At most 128 characters.",
    );
  });
});
