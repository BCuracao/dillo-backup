"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Database,
  HardDrive,
  LayoutDashboard,
  Settings,
} from "lucide-react";
import { useTranslations } from "next-intl";
import LanguageSwitcher from "./LanguageSwitcher";

interface NavItem {
  key: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { key: "dashboard", href: "/", icon: <LayoutDashboard size={18} /> },
  { key: "drives", href: "/drives", icon: <HardDrive size={18} /> },
  { key: "logs", href: "/logs", icon: <Database size={18} /> },
  { key: "settings", href: "/settings", icon: <Settings size={18} /> },
];

export default function Sidebar() {
  const t = useTranslations("sidebar");
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-card-border bg-card">
      {/* Logo */}
      <Link
        href="/"
        className="flex items-center gap-4 border-b border-card-border px-6 py-6 transition-colors hover:bg-white/[0.02]"
      >
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent/10 ring-1 ring-accent/20">
          <Image
            src="/dillo-logo.png"
            alt="Dillo Backup"
            width={36}
            height={36}
            className="invert brightness-200"
          />
        </div>
        <div>
          <h1 className="text-base font-bold tracking-tight text-foreground">
            {t("brand")}
          </h1>
          {t("brandSub") && (
            <p className="text-xs text-muted">{t("brandSub")}</p>
          )}
        </div>
      </Link>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.key}
              href={item.href}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-accent/10 font-medium text-accent"
                  : "text-muted hover:bg-white/5 hover:text-foreground"
              }`}
            >
              {item.icon}
              {t(`nav.${item.key}`)}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-card-border px-6 py-4">
        <div className="mb-3">
          <LanguageSwitcher />
        </div>
        <p className="text-[11px] text-muted">{t("version")}</p>
      </div>
    </aside>
  );
}
