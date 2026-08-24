import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import type { AuthProfile, Role } from "./api-types";
import { isSupabaseConfigured, supabase } from "./supabase";

export const API_BASE = import.meta.env["VITE_API_BASE_URL"] || "http://127.0.0.1:8000";

const TOKEN_STORAGE_KEY = "vqc_access_token";
const DEV_ROLE_STORAGE_KEY = "vqc_dev_role";
const LOGGED_IN_STORAGE_KEY = "vqc_logged_in";

// Everything below prefixed "dev" only runs when VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY are
// unset (isSupabaseConfigured === false) — it mirrors backend/app/auth.py's X-Dev-Role bypass so
// QC screens stay testable locally before a real Supabase project is wired up.
function readStoredToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function readStoredLoggedIn(): boolean {
  try {
    return (
      window.localStorage.getItem(LOGGED_IN_STORAGE_KEY) === "1" ||
      window.sessionStorage.getItem(LOGGED_IN_STORAGE_KEY) === "1"
    );
  } catch {
    return false;
  }
}

function readStoredDevRole(): Role {
  try {
    const stored = window.localStorage.getItem(DEV_ROLE_STORAGE_KEY);
    return stored === "QC_SUPERVISOR" ? "QC_SUPERVISOR" : "QC_OPERATOR";
  } catch {
    return "QC_OPERATOR";
  }
}

/** Maps common Supabase Auth error strings to Vietnamese for the login/register UI. */
function translateAuthError(message: string): string {
  const known: Record<string, string> = {
    "Invalid login credentials": "Sai email hoặc mật khẩu.",
    "Email not confirmed": "Email chưa được xác nhận. Vui lòng kiểm tra hộp thư.",
    "User already registered": "Email này đã được đăng ký. Vui lòng đăng nhập.",
    "Password should be at least 6 characters": "Mật khẩu phải có ít nhất 6 ký tự.",
    "Unable to validate email address: invalid format": "Định dạng email không hợp lệ.",
    "For security purposes, you can only request this after 60 seconds":
      "Vì lý do bảo mật, vui lòng thử lại sau 60 giây.",
  };
  return known[message] || message;
}

type AuthContextValue = {
  /** false when VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY are unset — dev-bypass mode instead. */
  supabaseReady: boolean;
  /** Still resolving the initial Supabase session on first load. */
  authBusy: boolean;
  token: string;
  devRole: Role;
  setDevRole: (value: Role) => void;
  setDevToken: (value: string) => void;
  authedFetch: (path: string, init?: RequestInit, timeoutMs?: number) => Promise<Response>;
  profile: AuthProfile | null;
  role: Role;
  isError: boolean;
  loggedIn: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signUp: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<{ error: string | null; needsEmailConfirmation: boolean }>;
  sendPasswordReset: (email: string) => Promise<{ error: string | null }>;
  updatePassword: (newPassword: string) => Promise<{ error: string | null }>;
  /** Dev-bypass-only quick login (no Supabase project configured yet). */
  devLogin: (role: Role) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [sessionLoaded, setSessionLoaded] = useState(!isSupabaseConfigured);
  const [devToken, setDevTokenState] = useState("");
  const [devRole, setDevRoleState] = useState<Role>("QC_OPERATOR");
  const [devLoggedIn, setDevLoggedInState] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) {
      setDevTokenState(readStoredToken());
      setDevRoleState(readStoredDevRole());
      setDevLoggedInState(readStoredLoggedIn());
      return;
    }
    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setSessionLoaded(true);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setSessionLoaded(true);
      void queryClient.invalidateQueries();
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [queryClient]);

  const token = isSupabaseConfigured ? session?.access_token || "" : devToken;
  const loggedIn = isSupabaseConfigured ? !!session : devLoggedIn;

  const setDevRole = useCallback(
    (value: Role) => {
      setDevRoleState(value);
      try {
        window.localStorage.setItem(DEV_ROLE_STORAGE_KEY, value);
      } catch {
        // ignore
      }
      void queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const setDevToken = useCallback(
    (value: string) => {
      setDevTokenState(value);
      try {
        if (value) window.localStorage.setItem(TOKEN_STORAGE_KEY, value);
        else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      } catch {
        // localStorage may be unavailable (private mode); in-memory token still works this session.
      }
      void queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const authedFetch = useCallback(
    (path: string, init: RequestInit = {}, timeoutMs = 8000) =>
      fetch(`${API_BASE}${path}`, {
        ...init,
        signal: init.signal || AbortSignal.timeout(timeoutMs),
        headers: {
          ...(init.headers || {}),
          ...(token ? { Authorization: `Bearer ${token}` } : { "X-Dev-Role": devRole }),
        },
      }),
    [token, devRole],
  );

  const profileQuery = useQuery({
    queryKey: ["auth", "me", token, devRole],
    queryFn: async () => {
      const response = await authedFetch("/api/auth/me");
      if (!response.ok) throw new Error(`auth failed (${response.status})`);
      return (await response.json()) as AuthProfile;
    },
    enabled: sessionLoaded && (loggedIn || !isSupabaseConfigured),
    retry: false,
    refetchInterval: 30_000,
  });

  const profile = profileQuery.data ?? null;
  // Least-privilege default: an unresolved/missing profile is treated as QC_OPERATOR, never
  // QC_SUPERVISOR — the supervisor console is only reachable once the backend confirms the role.
  const role: Role = profile?.role === "QC_SUPERVISOR" ? "QC_SUPERVISOR" : "QC_OPERATOR";

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) {
      return { error: "Supabase chưa được cấu hình (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY)." };
    }
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error: error ? translateAuthError(error.message) : null };
  }, []);

  const signUp = useCallback(async (email: string, password: string, fullName: string) => {
    if (!supabase) {
      return {
        error: "Supabase chưa được cấu hình (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).",
        needsEmailConfirmation: false,
      };
    }
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: `${window.location.origin}/login`,
      },
    });
    if (error) return { error: translateAuthError(error.message), needsEmailConfirmation: false };
    // Supabase returns no session when "Confirm email" is enabled on the project — the account
    // exists but can't sign in until the user clicks the confirmation link.
    return { error: null, needsEmailConfirmation: !data.session };
  }, []);

  const sendPasswordReset = useCallback(async (email: string) => {
    if (!supabase) return { error: "Supabase chưa được cấu hình." };
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    return { error: error ? translateAuthError(error.message) : null };
  }, []);

  const updatePassword = useCallback(async (newPassword: string) => {
    if (!supabase) return { error: "Supabase chưa được cấu hình." };
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    return { error: error ? translateAuthError(error.message) : null };
  }, []);

  const devLogin = useCallback(
    (chosenRole: Role) => {
      setDevRole(chosenRole);
      try {
        window.localStorage.setItem(LOGGED_IN_STORAGE_KEY, "1");
      } catch {
        // ignore
      }
      setDevLoggedInState(true);
    },
    [setDevRole],
  );

  const logout = useCallback(() => {
    if (isSupabaseConfigured && supabase) {
      void supabase.auth.signOut();
    }
    setDevTokenState("");
    try {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(LOGGED_IN_STORAGE_KEY);
      window.sessionStorage.removeItem(LOGGED_IN_STORAGE_KEY);
    } catch {
      // ignore
    }
    setDevLoggedInState(false);
    void queryClient.invalidateQueries();
  }, [queryClient]);

  return (
    <AuthContext.Provider
      value={{
        supabaseReady: isSupabaseConfigured,
        authBusy: !sessionLoaded,
        token,
        devRole,
        setDevRole,
        setDevToken,
        authedFetch,
        profile,
        role,
        isError: profileQuery.isError,
        loggedIn,
        signIn,
        signUp,
        sendPasswordReset,
        updatePassword,
        devLogin,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** The name to show for a profile everywhere in the UI — full name first, since email/user_id
 * are just fallbacks for accounts that signed up before `full_name` existed. */
export function profileDisplayName(profile: AuthProfile | null | undefined): string {
  return profile?.full_name || profile?.email || profile?.user_id || "Chưa đăng nhập";
}

export function assetUrl(pathOrUrl: string | null | undefined): string | undefined {
  if (!pathOrUrl) return undefined;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) return pathOrUrl;
  return `${API_BASE}${pathOrUrl.startsWith("/") ? "" : "/"}${pathOrUrl}`;
}
