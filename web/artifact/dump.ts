import { writeFileSync } from "node:fs";

import { loadBundle } from "../src/lib/bundle";

writeFileSync(process.argv[2], JSON.stringify(loadBundle()));
