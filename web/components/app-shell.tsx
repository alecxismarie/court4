"use client";

import { Activity, BarChart3, Home, Settings, Trophy, Upload, UserRound } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { usePlayerProfile } from "@/lib/use-player-profile";

const navItems = [
  { href: "/", label: "Dashboard", icon: Home, disabled: false },
  { href: "/performance", label: "Performance", icon: Activity, disabled: false },
  { href: "/matches", label: "Matches", icon: Trophy, disabled: false },
  { href: "/matches/upload", label: "Upload Match", icon: Upload, disabled: false },
  { href: "/player", label: "Player", icon: UserRound, disabled: false },
  { href: "/settings", label: "Settings", icon: Settings, disabled: false },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { profile } = usePlayerProfile();
  const playerLabel = profile.displayName || "Local Player";

  return (
    <div className="min-h-screen bg-[#eef4f0]">
      <header className="border-b border-court-line bg-white md:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-semibold" aria-label="Court4 dashboard">
            <Image
              src="/brand/court4-logo-64.png"
              alt=""
              width={64}
              height={64}
              className="h-11 w-11 object-contain"
              priority
            />
            <span>Court4</span>
          </Link>
          <span className="max-w-[11rem] truncate rounded-md border border-court-line px-3 py-1 text-sm text-court-muted">
            {playerLabel}
          </span>
        </div>
        <nav aria-label="Primary navigation" className="grid grid-cols-3 gap-1 px-3 pb-3">
          {navItems.map((item) => (
            <NavLink
              key={item.href}
              href={item.href}
              label={item.label}
              active={isActive(pathname, item.href)}
              disabled={item.disabled}
              icon={<item.icon aria-hidden="true" className="h-4 w-4" />}
              compact
            />
          ))}
        </nav>
      </header>

      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-72 shrink-0 border-r border-court-line bg-white md:block">
          <div className="sticky top-0 flex h-screen flex-col px-5 py-6">
            <Link href="/" className="mb-8 block" aria-label="Court4 dashboard">
              <Image
                src="/brand/court4-logo.png"
                alt="Court4 - Know Your Game"
                width={512}
                height={512}
                className="h-auto w-44 object-contain"
                priority
              />
            </Link>

            <nav aria-label="Primary navigation" className="space-y-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  active={isActive(pathname, item.href)}
                  disabled={item.disabled}
                  icon={<item.icon aria-hidden="true" className="h-4 w-4" />}
                />
              ))}
            </nav>

            <div className="mt-auto rounded-md border border-court-line bg-court-panel p-4">
              <div className="flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-md bg-white text-court-blue">
                  <BarChart3 aria-hidden="true" className="h-5 w-5" />
                </span>
                <div>
                  <p className="max-w-36 truncate text-sm font-medium text-court-ink">
                    {playerLabel}
                  </p>
                  <p className="text-xs text-court-muted">Browser-local workspace</p>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

function NavLink({
  href,
  label,
  active,
  disabled,
  icon,
  compact = false,
}: {
  href: string;
  label: string;
  active: boolean;
  disabled: boolean;
  icon: ReactNode;
  compact?: boolean;
}) {
  const classes = cn(
    "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    compact && "min-h-10 justify-center px-2 text-center text-xs sm:text-sm",
    active
      ? "bg-court-lime text-court-navy"
      : "text-court-muted hover:bg-court-panel hover:text-court-ink",
    disabled && "pointer-events-none opacity-45",
  );

  if (disabled) {
    return (
      <span aria-disabled="true" className={classes}>
        {icon}
        {label}
      </span>
    );
  }
  return (
    <Link href={href} className={classes} aria-current={active ? "page" : undefined}>
      {icon}
      {label}
    </Link>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  if (href === "/matches") {
    return pathname === "/matches" || (pathname.startsWith("/matches/") && !pathname.startsWith("/matches/upload"));
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
