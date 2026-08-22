import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  Navigate,
  createRootRouteWithContext,
  useRouter,
  useRouterState,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { QcShell } from "../components/qc/QcShell";
import { AuthProvider, useAuth } from "../lib/auth";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="font-mono text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Screen not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This station screen doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-sm border border-info/40 bg-info/10 px-4 py-2 font-mono text-xs tracking-[0.14em] text-info"
          >
            BACK TO SHIFT OVERVIEW
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This screen didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The station console hit an error. Try reloading the view.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-sm border border-info/40 bg-info/10 px-4 py-2 font-mono text-xs tracking-[0.14em] text-info"
          >
            RETRY
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-sm border border-border px-4 py-2 font-mono text-xs tracking-[0.14em] text-muted-foreground"
          >
            GO HOME
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "AUTO QC — Surface Inspection Station" },
      {
        name: "description",
        content:
          "AI computer-vision QC console for automotive body surface inspection with human-in-the-loop review.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap",
      },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
          {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
          <Outlet />
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const { token, isError, logout, loggedIn, role, profile } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const sessionExpired = !!token && isError;

  useEffect(() => {
    if (sessionExpired) logout();
  }, [sessionExpired, logout]);

  if (pathname === "/login" || pathname === "/reset-password") return <>{children}</>;

  // Unauthenticated users are sent to the login screen, which routes them by role
  // (QC_OPERATOR -> "/", QC_SUPERVISOR -> "/supervisor") once they sign in.
  if (!loggedIn) return <Navigate to="/login" />;

  // The QC_SUPERVISOR console (/supervisor/*) brings its own SupervisorShell layout — see
  // routes/supervisor/route.tsx. RBAC: only profiles.role === QC_SUPERVISOR may render it;
  // QC_OPERATOR is bounced to "/" (backend/app/auth.py enforces the same rule server-side on
  // every write endpoint, so this is a UX guard, not the security boundary). Supervisors keep
  // manual access to the inspector shell (see the switch link in SupervisorShell).
  if (pathname.startsWith("/supervisor")) {
    if (!profile) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-background">
          <span className="font-mono text-xs tracking-[0.14em] text-muted-foreground">
            ĐANG XÁC THỰC...
          </span>
        </div>
      );
    }
    if (role !== "QC_SUPERVISOR") return <Navigate to="/" />;
    return <>{children}</>;
  }

  return <QcShell>{children}</QcShell>;
}
