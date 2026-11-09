"use client";

import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";

/** Shows a load error, plus a loading message until the first result arrives. */
export function LoadState({
  loading,
  error,
  hasData,
}: {
  loading: boolean;
  error?: MessageKey;
  hasData: boolean;
}) {
  const { t } = useI18n();
  return (
    <>
      {error && (
        <p className="banner" role="alert">
          {hasData ? t("refresh_failed") : t(error)}
        </p>
      )}
      {loading && !hasData && <p className="muted">{t("loading")}</p>}
    </>
  );
}
