import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

// Slidev looks for `vite.config.*` next to the entry deck, not at the repository root.
//
// The deck's figures are pytask products under `bld/`, which sits outside this
// directory. Serving `bld/` as the public directory lets a slide reference a figure by
// a root-relative URL (`/kdu_vs_wohngeld/....png`); a `../../bld/...` path is resolved
// against the server root instead and never reaches the file.
export default defineConfig({
  publicDir: fileURLToPath(new URL("../bld", import.meta.url)),
});
