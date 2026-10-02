import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";
import jsxA11y from "eslint-plugin-jsx-a11y";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: [".next/**", ".next-*/**", "node_modules/**", "playwright-report/**", "test-results/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  // GAH-304 (Barrierefreiheit, Abschnitt 16): the jsx-a11y recommended rules on top of the
  // subset in next/core-web-vitals.
  { files: ["**/*.tsx"], rules: { ...jsxA11y.configs.recommended.rules } },
];

export default config;
