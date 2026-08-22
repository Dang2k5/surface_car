import { createFileRoute, Navigate, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Eye, EyeOff, Lock, Mail, ScanLine, User } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import heroVisual from "@/assets/qc-vision.jpg";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Đăng nhập | AUTO QC — Surface Vision AI" },
      {
        name: "description",
        content:
          "Đăng nhập hệ thống AUTO QC — kiểm định bề mặt thân vỏ ô tô bằng AI, dành cho QC trưởng.",
      },
      { property: "og:title", content: "Đăng nhập | AUTO QC — Surface Vision AI" },
      {
        property: "og:description",
        content: "Cổng đăng nhập hệ thống kiểm định bề mặt thân vỏ ô tô bằng AI.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LoginPage,
});

type Mode = "login" | "register" | "forgot";

function LoginPage() {
  const {
    supabaseReady,
    loggedIn,
    role,
    devRole,
    setDevRole,
    signIn,
    signUp,
    sendPasswordReset,
    devLogin,
  } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>("login");
  const [submitting, setSubmitting] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [confirmEmailPending, setConfirmEmailPending] = useState(false);
  const [resetEmailSent, setResetEmailSent] = useState(false);

  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginError, setLoginError] = useState("");

  const [fullName, setFullName] = useState("");
  const [regAccount, setRegAccount] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regPasswordConfirm, setRegPasswordConfirm] = useState("");
  const [regError, setRegError] = useState("");

  const [forgotAccount, setForgotAccount] = useState("");
  const [forgotError, setForgotError] = useState("");

  if (loggedIn) {
    // role defaults to QC_OPERATOR until the backend confirms profiles.role, so operators land on
    // "/" immediately; this re-renders (and re-navigates) to "/supervisor" once the role resolves.
    return <Navigate to={role === "QC_SUPERVISOR" ? "/supervisor" : "/"} />;
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError("");
    if (!supabaseReady) {
      devLogin(devRole);
      return;
    }
    setSubmitting(true);
    const { error } = await signIn(account.trim(), password);
    setSubmitting(false);
    if (error) setLoginError(error);
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setRegError("");
    if (regPassword !== regPasswordConfirm) {
      setRegError("Mật khẩu xác nhận không khớp.");
      return;
    }
    if (!supabaseReady) {
      setRegError("Supabase chưa được cấu hình — không thể đăng ký tài khoản thật ở chế độ dev.");
      return;
    }
    setSubmitting(true);
    const { error, needsEmailConfirmation } = await signUp(
      regAccount.trim(),
      regPassword,
      fullName.trim(),
    );
    setSubmitting(false);
    if (error) {
      setRegError(error);
      return;
    }
    setConfirmEmailPending(needsEmailConfirmation);
    setRegistered(true);
    setMode("login");
    setAccount(regAccount.trim());
    setRegAccount("");
    setRegPassword("");
    setRegPasswordConfirm("");
    setFullName("");
  }

  async function handleForgotPassword(e: React.FormEvent) {
    e.preventDefault();
    setForgotError("");
    if (!supabaseReady) {
      setForgotError("Supabase chưa được cấu hình — không thể gửi email đặt lại mật khẩu.");
      return;
    }
    setSubmitting(true);
    const { error } = await sendPasswordReset(forgotAccount.trim());
    setSubmitting(false);
    if (error) {
      setForgotError(error);
      return;
    }
    setResetEmailSent(true);
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

      <div className="relative grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
        <section className="relative hidden overflow-hidden border-r border-border lg:flex lg:flex-col lg:p-14">
          <img
            src={heroVisual}
            alt="Hệ thống AI kiểm tra bề mặt thân vỏ ô tô tại trạm kiểm định"
            width={1024}
            height={1280}
            className="absolute inset-0 h-full w-full object-cover opacity-90"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-background/75 via-background/15 to-background/85" />

          {/* AI vision scan overlay — sweeping scan line + viewfinder brackets over the surface shot */}
          <div className="animate-scan absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-info to-transparent shadow-[0_0_16px_var(--info)]" />
          <div className="pointer-events-none absolute inset-12 lg:inset-16">
            <span className="animate-frame-pulse absolute left-0 top-0 size-8 border-l-2 border-t-2 border-info/80" />
            <span className="animate-frame-pulse absolute right-0 top-0 size-8 border-r-2 border-t-2 border-info/80" />
            <span className="animate-frame-pulse absolute bottom-0 left-0 size-8 border-b-2 border-l-2 border-info/80" />
            <span className="animate-frame-pulse absolute bottom-0 right-0 size-8 border-b-2 border-r-2 border-info/80" />
          </div>

          <div className="relative flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-sm border border-info/50 bg-card/70 text-info">
              <ScanLine className="size-6" />
            </span>
            <span className="font-mono text-lg font-bold uppercase tracking-[0.28em] text-foreground">
              AUTO QC · Surface Vision AI
            </span>
          </div>
        </section>

        <section className="relative flex items-center justify-center overflow-hidden px-6 py-14 sm:px-12">
          <img
            src={heroVisual}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 -z-10 h-full w-full object-cover opacity-25 lg:opacity-20"
          />
          <div className="absolute inset-0 -z-10 bg-gradient-to-l from-background/40 via-background/70 to-background/95" />

          <div className="panel w-full max-w-lg p-10 backdrop-blur-xl sm:p-12">
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <span className="flex size-9 items-center justify-center rounded-sm border border-info/50 text-info">
                <ScanLine className="size-5" />
              </span>
              <span className="font-mono text-sm font-bold uppercase tracking-[0.28em]">
                AUTO QC · Surface Vision AI
              </span>
            </div>

            {!supabaseReady ? (
              <div className="mb-6 rounded-sm border border-warning/40 bg-warning/10 px-4 py-3 text-xs leading-snug text-warning">
                Chưa cấu hình Supabase (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY). Đang dùng chế
                độ dev-bypass — chọn vai trò bên dưới rồi bấm Đăng nhập.
              </div>
            ) : null}

            {mode !== "forgot" ? (
              <div className="flex items-center gap-1 rounded-sm border border-border bg-surface-2/60 p-1">
                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className={cn(
                    "flex-1 rounded-sm py-2.5 text-sm font-semibold tracking-wide transition-colors",
                    mode === "login"
                      ? "bg-info/15 text-info glow-info"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Đăng nhập
                </button>
                <button
                  type="button"
                  onClick={() => setMode("register")}
                  className={cn(
                    "flex-1 rounded-sm py-2.5 text-sm font-semibold tracking-wide transition-colors",
                    mode === "register"
                      ? "bg-info/15 text-info glow-info"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Đăng ký
                </button>
              </div>
            ) : null}

            {mode === "login" ? (
              <>
                {registered ? (
                  <div className="mt-6 rounded-sm border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
                    {confirmEmailPending
                      ? "Đăng ký thành công. Vui lòng kiểm tra email để xác nhận tài khoản trước khi đăng nhập."
                      : "Đăng ký thành công. Vui lòng đăng nhập bằng tài khoản vừa tạo."}
                  </div>
                ) : null}

                {loginError ? (
                  <div className="mt-6 rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {loginError}
                  </div>
                ) : null}

                <form className="mt-8 space-y-6" onSubmit={handleLogin}>
                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Mã nhân sự / Email</div>
                    <div className="relative">
                      <User className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="account"
                        type="email"
                        autoComplete="username"
                        placeholder="qc.inspector@company.com"
                        value={account}
                        onChange={(e) => setAccount(e.target.value)}
                        required
                        disabled={!supabaseReady}
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)] disabled:opacity-50"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Mật khẩu</div>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        disabled={!supabaseReady}
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-11 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)] disabled:opacity-50"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                        className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-info"
                      >
                        {showPassword ? (
                          <EyeOff className="size-4.5" />
                        ) : (
                          <Eye className="size-4.5" />
                        )}
                      </button>
                    </div>
                  </div>

                  {!supabaseReady ? (
                    <div className="space-y-1">
                      <div className="label-caps text-[12px]">Vai trò dev (chưa có Supabase)</div>
                      <select
                        value={devRole}
                        onChange={(e) => setDevRole(e.target.value as typeof devRole)}
                        className="h-11 w-full rounded-sm border border-border bg-surface-2/60 px-3 font-mono text-xs text-foreground"
                      >
                        <option value="QC_OPERATOR">QC_OPERATOR — QC Inspector</option>
                        <option value="QC_SUPERVISOR">QC_SUPERVISOR — QC Supervisor</option>
                      </select>
                    </div>
                  ) : null}

                  <div className="flex items-center justify-end pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        setForgotAccount(account);
                        setForgotError("");
                        setResetEmailSent(false);
                        setMode("forgot");
                      }}
                      className="text-sm text-info transition-opacity hover:opacity-75"
                    >
                      Quên mật khẩu?
                    </button>
                  </div>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="h-12 w-full rounded-sm border border-info/40 bg-info/10 font-mono text-base font-semibold uppercase tracking-[0.18em] text-info transition-all hover:bg-info/20 hover:shadow-[var(--glow-info)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {submitting ? "ĐANG ĐĂNG NHẬP..." : "Đăng nhập"}
                  </button>
                </form>
              </>
            ) : mode === "register" ? (
              <>
                <form className="mt-8 space-y-6" onSubmit={handleRegister}>
                  {regError ? (
                    <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      {regError}
                    </div>
                  ) : null}

                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Họ và tên</div>
                    <div className="relative">
                      <User className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="full-name"
                        autoComplete="name"
                        placeholder="Nguyễn Văn A"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        required
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Email</div>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="reg-account"
                        type="email"
                        autoComplete="username"
                        placeholder="qc.inspector@company.com"
                        value={regAccount}
                        onChange={(e) => setRegAccount(e.target.value)}
                        required
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Mật khẩu</div>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="reg-password"
                        type="password"
                        autoComplete="new-password"
                        placeholder="••••••••"
                        value={regPassword}
                        onChange={(e) => setRegPassword(e.target.value)}
                        required
                        minLength={8}
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="label-caps text-[12px]">Xác nhận mật khẩu</div>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                      <input
                        id="reg-password-confirm"
                        type="password"
                        autoComplete="new-password"
                        placeholder="••••••••"
                        value={regPasswordConfirm}
                        onChange={(e) => setRegPasswordConfirm(e.target.value)}
                        required
                        minLength={8}
                        className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                      />
                    </div>
                  </div>

                  <p className="text-[11px] leading-snug text-muted-foreground">
                    Tài khoản mới mặc định nhận vai trò QC Inspector (QC_OPERATOR). Chuyển sang QC
                    Supervisor là thao tác quản trị thủ công trong Supabase, không thực hiện qua
                    biểu mẫu này.
                  </p>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="h-12 w-full rounded-sm border border-info/40 bg-info/10 font-mono text-base font-semibold uppercase tracking-[0.18em] text-info transition-all hover:bg-info/20 hover:shadow-[var(--glow-info)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {submitting ? "ĐANG ĐĂNG KÝ..." : "Đăng ký"}
                  </button>
                </form>
              </>
            ) : (
              <>
                <h1 className="mt-2 text-lg font-semibold text-foreground">Quên mật khẩu</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  Nhập email tài khoản để nhận liên kết đặt lại mật khẩu.
                </p>

                {resetEmailSent ? (
                  <div className="mt-6 rounded-sm border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
                    Đã gửi email đặt lại mật khẩu tới {forgotAccount}. Vui lòng kiểm tra hộp thư.
                  </div>
                ) : (
                  <form className="mt-6 space-y-6" onSubmit={handleForgotPassword}>
                    {forgotError ? (
                      <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                        {forgotError}
                      </div>
                    ) : null}
                    <div className="space-y-2">
                      <div className="label-caps text-[12px]">Email</div>
                      <div className="relative">
                        <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4.5 -translate-y-1/2 text-muted-foreground" />
                        <input
                          id="forgot-account"
                          type="email"
                          autoComplete="username"
                          placeholder="qc.inspector@company.com"
                          value={forgotAccount}
                          onChange={(e) => setForgotAccount(e.target.value)}
                          required
                          className="h-12 w-full rounded-sm border border-input bg-surface-2/60 pl-11 pr-3 text-base text-foreground outline-none transition-shadow focus-visible:border-info/60 focus-visible:shadow-[var(--glow-info)]"
                        />
                      </div>
                    </div>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="h-12 w-full rounded-sm border border-info/40 bg-info/10 font-mono text-base font-semibold uppercase tracking-[0.18em] text-info transition-all hover:bg-info/20 hover:shadow-[var(--glow-info)] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {submitting ? "ĐANG GỬI..." : "Gửi email đặt lại mật khẩu"}
                    </button>
                  </form>
                )}

                <button
                  type="button"
                  onClick={() => setMode("login")}
                  className="mt-6 text-sm text-info transition-opacity hover:opacity-75"
                >
                  ← Quay lại đăng nhập
                </button>
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
