import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Court 4",
  description:
    "Know your game, elevate every match.",
  icons: {
    icon: [
      {
        url: "/brand/court4-favicon-64.png?v=20260728",
        sizes: "64x64",
        type: "image/png",
      },
    ],
    apple: [
      {
        url: "/brand/court4-favicon-192.png?v=20260728",
        sizes: "192x192",
        type: "image/png",
      },
    ],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
