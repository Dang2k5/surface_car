import { createFileRoute, Navigate, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Eye, EyeOff, Lock, ScanLine } from "lucide-react";

import { useAuth } from "@/lib/auth";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";
import heroVisual from "@/assets/qc-vision.jpg";

export const Route = createFileRoute("/reset-password")({
  head: () => ({
    meta: [{ title: "Đặt lại mật khẩu | AUTO QC — Surface Vision AI" }],
  }),
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const { updatePassword } = useAuth();
  const navigate = useNavigate();

  // Supabase's password-recovery link signs the browser into a temporary "recovery" session —
  // wait for it before allowing the update form to submit.
  const [recoveryReady, setRecoveryReady] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setRecoveryReady(true);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY" || event === "SIGNED_IN") setRecoveryReady(true);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  if (!isSupabaseConfigured) return <Navigate to="/login" />;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (password !== confirm) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }
    setSubmitting(true);
    const { error: updateError } = await updatePassword(password);
    setSubmitting(false);
    if (updateError) {
      setError(updateError);
      return;
    }
    setDone(true);
  }

  return (
    <main className="relative min-h-screen bg-background">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(color-mix(in oklab, var(--info) 8%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in oklab, var(--info) 8%, transparent) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-14">
        <img
          src={heroVisual}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 -z-10 h-full w-full object-cover opacity-20"
        />
        <div className="absolute inset-0 -z-10 bg-gradient-to-l from-background/40 via-background/70 to-background/95" />

        <div className="panel w-full max-w-md p-10 backdrop-blur-xl sm:p-12">
          <div className="mb-8 flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-sm border border-info/50 text-info">
              <ScanLine className="size-5" />
            </span>
            <span className="font-mono text-sm font-bold uppercase tracking-[0.28em]">
              AUTO QC · Surface Vision AI
            </span>
          </div>

          <h1 className="text-lg font-semibold text-foreground">Đặt lại mật khẩu</h1>

          {done ? (
            <div className="mt-6 space-y-4">
              <div className="rounded-sm border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
                Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại.
              </div>
              <button
                type="button"
                onClick={() => void navigate({ to: "/login" })}
                className="h-12 w-full rounded-sm border border-info/40 bg-info/10 font-mono text-base font-semibold uppercase tracking-[0.18em] text-info transition-all hover:bg-info/20 hover:shadow-[var(--glow-info)]"
              >
                Về trang đăng nhập
              </button>
            </div>
          ) : !recoveryReady ? (
            <p className="mt-6 text-sm text-muted-foreground">
              Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Vui lòng yêu cầu một liên kết
              mới từ trang đăng nhập.
            </p>
          ) : (
            <form className="mt-6 space-y-6" onSubmit={handleSubmit}>
              {error ? (
                <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="label-caps text-[12px]">Mật khẩu mới</div>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-11 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-info"
                  >
                    {showPassword ? <EyeOff className="size-4.5" /> : <Eye className="size-4.5" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <div className="label-caps text-[12px]">Xác nhận mật khẩu mới</div>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                    minLength={8}
                    className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="h-12 w-full rounded-sm border border-info/40 bg-info/10 font-mono text-base font-semibold uppercase tracking-[0.18em] text-info transition-all hover:bg-info/20 hover:shadow-[var(--glow-info)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "ĐANG LƯU..." : "Lưu mật khẩu mới"}
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
