import { createRoot } from "react-dom/client";

import Dashboard from "../src/components/Dashboard";
import type { Bundle } from "../src/lib/types";

const el = document.getElementById("hom-data");
const bundle = JSON.parse(el?.textContent ?? "null") as Bundle;
createRoot(document.getElementById("root")!).render(<Dashboard bundle={bundle} />);
