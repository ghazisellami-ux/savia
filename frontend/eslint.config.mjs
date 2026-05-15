import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  // Relax strict rules for faster development
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "warn", // Changed from error to warn
      "@typescript-eslint/no-unused-vars": "warn", // Changed from error to warn
      "react/no-unescaped-entities": "warn", // Changed from error to warn
      "react-hooks/exhaustive-deps": "warn", // Changed from error to warn
      "react-hooks/set-state-in-effect": "warn", // Changed from error to warn
      "react-hooks/preserve-manual-memoization": "warn", // Changed from error to warn
      "@next/next/no-img-element": "warn", // Changed from error to warn
      "@next/next/no-page-custom-font": "warn", // Changed from error to warn
      "@typescript-eslint/no-require-imports": "warn", // Changed from error to warn
      "import/no-anonymous-default-export": "warn", // Changed from error to warn
      "prefer-const": "warn", // Changed from error to warn
    },
  },
]);

export default eslintConfig;
