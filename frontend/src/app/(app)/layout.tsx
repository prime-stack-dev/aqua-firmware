"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { LanguagePicker } from "@/components/LanguagePicker";
import { api, errorKey, hasSession, IS_DEMO, logout } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import { RoleContext } from "@/lib/session";
import type { Me } from "@/lib/types";

const NAV: { href: string; label: MessageKey }[] = [
  { href: "/", label: "nav_home" },
  { href: "/alerts", label: "nav_alerts" },
  { href: "/alert-rules", label: "nav_limits" },
  { href: "/devices", label: "nav_devices" },
  { href: "/subscriptions", label: "nav_plans" },
];

function Centered({ children }: { children: ReactNode }) {
  return (
    <main className="login">
      <div className="card stack">{children}</div>
    </main>
  );
}

function Brand() {
  return (
    <div className="brand">
      Aqua <span>OS</span>
    </div>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const { t } = useI18n();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<MessageKey>();

  useEffect(() => {
    if (!hasSession()) {
      router.replace("/login");
      return;
    }
    api<Me>("/me")
      .then(setMe)
      .catch((caught) => setError(errorKey(caught)));
  }, [router]);

  if (error) {
    return (
      <Centered>
        <p className="banner" role="alert">
          {t(error)}
        </p>
        <button onClick={() => void logout()}>{t("back_to_login")}</button>
      </Centered>
    );
  }
  if (!me) {
    return (
      <Centered>
        <p className="muted">{t("loading")}</p>
      </Centered>
    );
  }

  const organization = me.organizations.find(
    (item) => item.organization_id === me.current_organization_id,
  );
  if (!organization) {
    return (
      <Centered>
        <h1>{t("admin_title")}</h1>
        <p className="muted">{t("admin_text")}</p>
        <button onClick={() => void logout()}>{t("logout")}</button>
      </Centered>
    );
  }

  const isActive = (href: string) =>
    path === href || (href === "/" && path.startsWith("/ponds"));

  return (
    <RoleContext.Provider value={organization.role}>
      <div className="app">
        <nav className="rail" aria-label="Main">
          <Brand />
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={isActive(item.href) ? "active" : undefined}
              aria-current={isActive(item.href) ? "page" : undefined}
            >
              {t(item.label)}
            </Link>
          ))}
        </nav>
        <div className="content">
          <header className="topbar">
            <div className="top-brand">
              <Brand />
            </div>
            <span className="who muted small">{organization.organization_name}</span>
            <LanguagePicker />
            {!IS_DEMO && <button onClick={() => void logout()}>{t("logout")}</button>}
          </header>
          <main className="main">
            {IS_DEMO && (
              <p className="banner demo" role="status">
                {t("demo_banner")}
              </p>
            )}
            {children}
          </main>
        </div>
      </div>
    </RoleContext.Provider>
  );
}
