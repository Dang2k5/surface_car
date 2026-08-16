import { spawn } from "node:child_process";
import { join } from "node:path";

const command = process.platform === "win32" ? "vinext.cmd" : "vinext";
const executable = join(process.cwd(), "node_modules", ".bin", command);
const args = process.argv.slice(2);
const child = process.platform === "win32"
  ? spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", `${executable} ${args.join(" ")}`], {
      stdio: "inherit",
      env: { ...process.env, WRANGLER_LOG_PATH: ".wrangler/wrangler.log" },
    })
  : spawn(executable, args, {
  stdio: "inherit",
  env: { ...process.env, WRANGLER_LOG_PATH: ".wrangler/wrangler.log" },
  });

child.on("exit", (code) => process.exit(code ?? 1));
