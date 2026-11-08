/**
 * Server-side snapshot loader. Verifies each file's SHA-256 against the manifest, then
 * validates every row with its Zod schema. Throws on any mismatch: the UI must never
 * render unverified numbers.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

import { DATASET_SCHEMAS, type DatasetName, Manifest, type Row } from "./schemas";

const DATA_DIR = path.join(process.cwd(), "public", "data", "current");

export function loadManifest() {
  return Manifest.parse(JSON.parse(readFileSync(path.join(DATA_DIR, "manifest.json"), "utf8")));
}

export function loadDataset<N extends DatasetName>(name: N): Row<N>[] {
  const manifest = loadManifest();
  const entry = manifest.files.find((f) => f.dataset === name);
  if (!entry) throw new Error(`dataset ${name} not in manifest`);
  const text = readFileSync(path.join(DATA_DIR, entry.file), "utf8");
  const digest = createHash("sha256").update(text).digest("hex");
  if (digest !== entry.sha256) throw new Error(`checksum mismatch for ${name}`);
  const rows = JSON.parse(text) as unknown[];
  if (rows.length !== entry.rows) throw new Error(`row count mismatch for ${name}`);
  const schema = DATASET_SCHEMAS[name];
  return rows.map((r, i) => {
    const parsed = schema.safeParse(r);
    if (!parsed.success) {
      throw new Error(`${name} row ${i}: ${parsed.error.issues[0]?.message}`);
    }
    return parsed.data as Row<N>;
  });
}
