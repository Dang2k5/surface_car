import { useState } from "react";
import { KeyRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/api-types";

export function IdentityPanel() {
  const { supabaseReady, token, setDevToken, devRole, setDevRole, isError } = useAuth();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(token);

  if (supabaseReady) {
    // Real Supabase session — the access token is managed by the SDK, not editable here.
    // Already summarized by the profile card above (QcShell), no separate session panel needed.
    return null;
  }

  return (
    <div className="rounded-sm border border-border bg-surface-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] text-muted-foreground">
          <KeyRound className="size-3.5" /> ACCESS TOKEN
        </span>
        {isError ? (
          <span className="rounded-sm border border-destructive/40 bg-destructive/10 px-1.5 font-mono text-[10px] text-destructive">
            BỊ TỪ CHỐI
          </span>
        ) : (
          <span className="rounded-sm border border-border px-1.5 font-mono text-[10px] text-muted-foreground">
            {open ? "ẨN" : "SỬA"}
          </span>
        )}
      </button>
      {open ? (
        <div className="space-y-2 border-t border-border p-3">
          <input
            type="password"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Supabase access token"
            className="w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground"
          />
          <div className="flex gap-2">
            <button
              onClick={() => setDevToken(draft)}
              className="flex-1 rounded-sm border border-info/40 bg-info/10 px-2 py-1.5 font-mono text-[11px] tracking-[0.1em] text-info"
            >
              ÁP DỤNG
            </button>
            {token ? (
              <button
                onClick={() => {
                  setDraft("");
                  setDevToken("");
                }}
                className="rounded-sm border border-border px-2 py-1.5 font-mono text-[11px] tracking-[0.1em] text-muted-foreground"
              >
                XÓA
              </button>
            ) : null}
          </div>
          {!token ? (
            <div className="space-y-1">
              <div className="label-caps">Vai trò dev (chưa có token)</div>
              <select
                value={devRole}
                onChange={(e) => setDevRole(e.target.value as Role)}
                className="w-full rounded-sm border border-border bg-background px-2 py-1.5 font-mono text-xs text-foreground"
              >
                <option value="QC_SUPERVISOR">QC_SUPERVISOR</option>
                <option value="QC_OPERATOR">QC_OPERATOR</option>
              </select>
            </div>
          ) : null}
          <p className={cn("text-[11px] leading-snug text-muted-foreground")}>
            Dán JWT của Supabase để đăng nhập với tài khoản thật, hoặc để trống để dùng header
            dev-role (chỉ hoạt động khi backend ở chế độ dev, chưa cấu hình VITE_SUPABASE_URL).
          </p>
        </div>
      ) : null}
    </div>
  );
}
