import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import type { Linter } from "eslint";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

// The repository's conventions (CLAUDE.md), as far as a linter can hold them.
// Each restriction carries the sentence it enforces, so a failing line says why.
const conventions: Linter.RulesRecord = {
  "@typescript-eslint/no-explicit-any": "error",
  // "No `as` to silence the compiler": data from the network is `unknown` until
  // a check narrows it. `as const` is still allowed — it widens nothing.
  "@typescript-eslint/consistent-type-assertions": ["error", { assertionStyle: "never" }],
  "@typescript-eslint/no-non-null-assertion": "error",
  // The event stream is one union on `type`; a switch over it must handle every
  // member, so a new event that is not handled does not pass.
  "@typescript-eslint/switch-exhaustiveness-check": [
    "error",
    { considerDefaultExhaustiveForUnions: false, requireDefaultForNonUnion: true },
  ],
  "no-nested-ternary": "error",
  "no-restricted-syntax": [
    "error",
    {
      selector: "ReturnStatement > ConditionalExpression",
      message: "Code reads as steps: branch with a real `if`, return at the end.",
    },
    {
      selector: "ArrowFunctionExpression > ConditionalExpression.body",
      message: "Code reads as steps: branch with a real `if`, return at the end.",
    },
    {
      selector: "JSXSpreadAttribute",
      message: "Pass each prop by name; a spread hides which fields are passed.",
    },
    {
      selector: "ObjectExpression > SpreadElement",
      message: "Name each field; a spread hides which fields are passed.",
    },
  ],
};

export default defineConfig([
  globalIgnores(["dist", "node_modules"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat["recommended-latest"],
      prettier,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: conventions,
  },
]);
