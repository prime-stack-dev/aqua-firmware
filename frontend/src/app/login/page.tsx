"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { LanguagePicker } from "@/components/LanguagePicker";
import { ApiError, errorKey, IS_DEMO, login } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [needsOrganization, setNeedsOrganization] = useState(false);
  const [error, setError] = useState<MessageKey>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (IS_DEMO) router.replace("/");
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await login(email, password, organizationId.trim() || undefined);
      router.replace("/");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setNeedsOrganization(true);
        setError("need_organization");
      } else if (caught instanceof ApiError && caught.status === 401) {
        setError("bad_login");
      } else {
        setError(errorKey(caught));
      }
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="card stack" onSubmit={submit}>
        <div className="brand">
          Aqua <span>OS</span>
        </div>
        <LanguagePicker />
        {error && (
          <p className="banner" role="alert">
            {t(error)}
          </p>
        )}
        <label>
          {t("email")}
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          {t("password")}
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {needsOrganization && (
          <label>
            {t("organization_id")}
            <input
              required
              value={organizationId}
              onChange={(event) => setOrganizationId(event.target.value)}
            />
          </label>
        )}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? t("logging_in") : t("login")}
        </button>
      </form>
    </main>
  );
}
