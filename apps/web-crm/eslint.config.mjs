import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";
import jsxA11y from "eslint-plugin-jsx-a11y";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: [".next/**", ".next-*/**", "node_modules/**", "playwright-report/**", "test-results/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  // S16-09 (Barrierefreiheit, Abschnitt 16): the jsx-a11y recommended rules on top of the
  // subset in next/core-web-vitals. The rules below still have findings in existing
  // components (15 on 30.09.2026) and stay off until those are fixed (docs/OPEN_QUESTIONS.md).
  {
    files: ["**/*.tsx"],
    rules: {
      ...jsxA11y.configs.recommended.rules,
      "jsx-a11y/no-autofocus": "off",
      "jsx-a11y/click-events-have-key-events": "off",
      "jsx-a11y/label-has-associated-control": "off",
      "jsx-a11y/interactive-supports-focus": "off",
      "jsx-a11y/no-static-element-interactions": "off",
      "jsx-a11y/no-noninteractive-element-interactions": "off",
    },
  },
];

export default config;
