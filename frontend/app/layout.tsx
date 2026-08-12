import type { Metadata } from "next";
import { headers } from "next/headers";
import globalStyles from "./globals.css?inline";
import workstationStyles from "./workstation.css?inline";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") || requestHeaders.get("host") || "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") || "http";
  return {
    metadataBase: new URL(`${protocol}://${host}`),
    title: "Visual QC Agent | FNS Workstation",
    description: "Model-backed QC workstation for FNS vehicle inspection workflows.",
    openGraph: {
      title: "Visual QC Agent",
      description: "FNS quality-control workstation with explainable AI workflow.",
      images: ["/og.png"],
    },
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <head>
        <style dangerouslySetInnerHTML={{ __html: globalStyles }} />
        <style dangerouslySetInnerHTML={{ __html: workstationStyles }} />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}
