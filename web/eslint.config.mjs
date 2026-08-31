import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettierConfig from "eslint-config-prettier";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettierConfig,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  // File-length enforcement (see root CLAUDE.md's file-length enforcement section). Test
  // files are exempt for the same reason backend tests/ is exempt from the equivalent
  // backend check: a long test file is usually many independent cases, not the mixed
  // responsibilities this rule targets.
  {
    rules: {
      "max-lines": [
        "error",
        { max: 400, skipBlankLines: false, skipComments: false },
      ],
    },
  },
  {
    files: ["**/*.test.ts", "**/*.test.tsx", "e2e/**/*.ts"],
    rules: {
      "max-lines": "off",
    },
  },
]);

export default eslintConfig;
