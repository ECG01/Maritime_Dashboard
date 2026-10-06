// The system prompt lives in system_prompt.md so the local dev server and the
// Worker cannot drift apart. Workers cannot read a file at runtime, so this
// bakes it into a module at build time.
//   node build-rules.mjs
import { readFileSync, writeFileSync } from "node:fs";
const text = readFileSync(new URL("./system_prompt.md", import.meta.url), "utf8").trim();
writeFileSync(
  new URL("./rules.generated.ts", import.meta.url),
  "// GENERATED from system_prompt.md by build-rules.mjs - do not edit.\n" +
    `export const RULES = ${JSON.stringify(text)};\n`,
);
console.log(`rules.generated.ts written (${text.length} chars)`);
