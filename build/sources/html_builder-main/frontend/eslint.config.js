import js from "@eslint/js";
import babelParser from "@babel/eslint-parser";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

/**
 * TypeScript 7 is not yet supported by typescript-eslint, so the Babel parser
 * supplies the TS/TSX syntax. Type errors are tsc's job (`npm run typecheck`);
 * ESLint here exists for the rules tsc cannot see — above all the hook
 * dependency arrays that were previously hand-maintained and unchecked.
 */
export default [
  { ignores: ["dist/**", "node_modules/**", "**/*.tsbuildinfo"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: babelParser,
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
      parserOptions: {
        requireConfigFile: false,
        // Parser plugins, not presets: ESLint only needs the syntax, and Babel 8's presets no longer
        // apply the TypeScript transform to code handed over by @babel/eslint-parser.
        babelOptions: {
          babelrc: false,
          configFile: false,
          parserOpts: { plugins: ["typescript", "jsx"] },
        },
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/rules-of-hooks": "error",
      // tsc owns these with strict + noUnused*; ESLint only double-reports them.
      "no-unused-vars": "off",
      "no-undef": "off",
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
];
