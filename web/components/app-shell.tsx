"use client";

import {
  ChartNoAxesCombined,
  ChevronDown,
  History,
  Home,
  LogOut,
  Settings,
  Upload,
  UserRound,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import { cn } from "@/lib/utils";
import { useOptionalAuth } from "@/lib/auth-context";
import { usePlayerProfile } from "@/lib/use-player-profile";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Home, disabled: false },
  { href: "/player", label: "Player", icon: UserRound, disabled: false },
  { href: "/upload-match", label: "Upload Match", icon: Upload, disabled: false },
  {
    href: "/analysis-history",
    label: "Analysis History",
    icon: History,
    disabled: false,
  },
  {
    href: "/my-progress",
    label: "My Progress",
    icon: ChartNoAxesCombined,
    disabled: false,
  },
  { href: "/settings", label: "Settings", icon: Settings, disabled: false },
] as const;

const mobileNavItems = [
  { href: "/dashboard", label: "Dashboard", icon: Home, disabled: false },
  { href: "/upload-match", label: "Upload", icon: Upload, disabled: false },
  { href: "/analysis-history", label: "History", icon: History, disabled: false },
  { href: "/my-progress", label: "Progress", icon: ChartNoAxesCombined, disabled: false },
] as const;

const activeRouteAliases: Partial<Record<(typeof navItems)[number]["href"], readonly string[]>> = {
  "/analysis-history": ["/matches"],
};

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const auth = useOptionalAuth();
  const { profile } = usePlayerProfile();
  const playerLabel = profile.displayName || "Local Player";
  const [accountOpen, setAccountOpen] = useState(false);
  const accountMenuId = useId();
  const accountMenu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!accountOpen) return;

    function closeOnOutsidePress(event: PointerEvent) {
      if (!accountMenu.current?.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAccountOpen(false);
      }
    }

    document.addEventListener("pointerdown", closeOnOutsidePress);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePress);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountOpen]);

  if (
    pathname === "/" ||
    pathname === "/login" ||
    pathname === "/register" ||
    pathname === "/forgot-password" ||
    pathname === "/reset-password" ||
    pathname === "/verification-pending" ||
    pathname === "/verify-email"
  ) {
    return children;
  }

  // AuthGate owns redirects, while AppShell ensures private navigation never
  // appears during session restoration or for a provisional account.
  if (!auth || auth.loading || !auth.user?.email_verified_at) {
    return children;
  }

  return (
    <div className="min-h-screen bg-[#eef4f0]">
      <header className="sticky top-0 z-40 border-b border-court-line bg-white/95 shadow-sm backdrop-blur md:hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <Link href="/dashboard" className="flex items-center gap-2 font-semibold" aria-label="Court4 dashboard">
            <Image
              src="/brand/court4-logo-64.png"
              alt=""
              width={64}
              height={64}
              className="h-10 w-10 object-contain"
              priority
            />
            <span className="text-base font-bold tracking-tight text-court-ink">Court4</span>
          </Link>
          <div ref={accountMenu} className="relative">
            <button
              type="button"
              aria-label={`Open account menu for ${playerLabel}`}
              aria-expanded={accountOpen}
              aria-controls={accountMenuId}
              aria-haspopup="menu"
              onClick={() => setAccountOpen((open) => !open)}
              className="flex max-w-[12rem] items-center gap-2 rounded-full border border-court-line bg-court-panel py-1 pl-1 pr-2 text-sm font-semibold text-court-ink shadow-sm transition hover:border-court-lime focus-visible:border-court-lime"
            >
              <ProfileAvatar profile={profile} className="h-8 w-8 border text-xs" />
              <span className="min-w-0 truncate">{playerLabel}</span>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  "h-4 w-4 shrink-0 text-court-muted transition",
                  accountOpen && "rotate-180",
                )}
              />
            </button>
            {accountOpen ? (
              <div
                id={accountMenuId}
                role="menu"
                aria-label="Player account"
                className="absolute right-0 top-[calc(100%+0.5rem)] w-52 overflow-hidden rounded-xl border border-court-line bg-white p-1.5 shadow-[0_18px_45px_rgba(6,31,56,0.18)]"
              >
                <p className="truncate px-3 pb-2 pt-1.5 text-xs text-court-muted">
                  {auth.user.email}
                </p>
                <AccountMenuLink
                  href="/player"
                  label="Player profile"
                  icon={<UserRound aria-hidden="true" className="h-4 w-4" />}
                  onSelect={() => setAccountOpen(false)}
                />
                <AccountMenuLink
                  href="/settings"
                  label="Settings"
                  icon={<Settings aria-hidden="true" className="h-4 w-4" />}
                  onSelect={() => setAccountOpen(false)}
                />
                <div className="my-1 border-t border-court-line" />
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    void auth.logout();
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm font-semibold text-red-700 transition hover:bg-red-50"
                >
                  <LogOut aria-hidden="true" className="h-4 w-4" />
                  Log out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <nav
        aria-label="Primary navigation"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-court-line bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] shadow-[0_-10px_30px_rgba(6,31,56,0.10)] backdrop-blur md:hidden"
      >
        {mobileNavItems.map((item) => (
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

      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-72 shrink-0 border-r border-court-line bg-white md:block">
          <div className="sticky top-0 flex h-screen flex-col px-5 py-6">
            <Link
              href="/dashboard"
              className="mb-8 flex justify-center"
              aria-label="Court4 dashboard"
            >
              <Image
                src="/brand/court4-logo.png"
                alt="Court4 - Know Your Game"
                width={1080}
                height={1350}
                className="h-auto w-52 object-contain"
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
            {auth?.user ? (
              <div className="mt-auto border-t border-court-line pt-4">
                <button
                  type="button"
                  onClick={() => void auth.logout()}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-court-muted hover:bg-court-panel hover:text-court-ink"
                >
                  <LogOut aria-hidden="true" className="h-4 w-4" />
                  Log out
                </button>
              </div>
            ) : null}
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 pb-28 pt-5 sm:px-6 md:py-6 lg:px-8">{children}</main>
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
    "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    compact && "min-h-16 flex-col justify-center gap-1 rounded-none px-1 py-2 text-center text-[0.6875rem]",
    active
      ? compact
        ? "text-court-navy"
        : "bg-court-lime text-court-navy"
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
      {compact ? (
        <span
          className={cn(
            "grid h-7 w-11 place-items-center rounded-full transition",
            active && "bg-court-lime/35",
          )}
        >
          {icon}
        </span>
      ) : icon}
      {label}
    </Link>
  );
}

function AccountMenuLink({
  href,
  label,
  icon,
  onSelect,
}: {
  href: string;
  label: string;
  icon: ReactNode;
  onSelect: () => void;
}) {
  return (
    <Link
      href={href}
      role="menuitem"
      onClick={onSelect}
      className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold text-court-ink transition hover:bg-court-panel"
    >
      {icon}
      {label}
    </Link>
  );
}

function isActive(pathname: string, href: (typeof navItems)[number]["href"]): boolean {
  if (href === "/dashboard") {
    return pathname === "/dashboard";
  }
  const routePrefixes = [href, ...(activeRouteAliases[href] ?? [])];
  return routePrefixes.some(
    (routePrefix) =>
      pathname === routePrefix || pathname.startsWith(`${routePrefix}/`),
  );
}
