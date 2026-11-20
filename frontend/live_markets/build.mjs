/** Build from any working directory; the Python command uses only the standard library. */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const result = spawnSync(process.env.PYTHON || "python3", ["-m", "src.hk.dashboard", "build"], {
  cwd: fileURLToPath(new URL("../../", import.meta.url)), env: process.env, stdio: "inherit",
});
if (result.error) { console.error(result.error.message); process.exit(1); }
process.exit(result.status ?? 1);
