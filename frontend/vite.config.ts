// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only, preset overridden to "vercel" below — see nitro option), VITE_* env
//     injection, @ path alias, React/TanStack dedupe, error logger plugins, and sandbox detection
//     (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  // Deploy target is Vercel, not Lovable's own Cloudflare Workers default — this repo's frontend
  // is deployed on Vercel (see docs/DEPLOYMENT_PLAN_AWS_GPU.md), which needs nitro's "vercel"
  // preset so `vite build` emits .vercel/output/ (Build Output API v3) instead of a Cloudflare
  // Worker + wrangler.json.
  nitro: {
    preset: "vercel",
  },
  // Only takes effect outside the Lovable cloud sandbox (which force-pins 8080) — local dev here
  // uses 8899 to avoid clashing with other services already bound to 8080 (this machine) and
  // 8888 (a locally-running Railway-deployed instance of this same app).
  vite: {
    server: { port: 8899, strictPort: true },
  },
});
