"use client";

import { LANGUAGES, useI18n } from "@/lib/i18n";

export function LanguagePicker() {
  const { language, setLanguage, t } = useI18n();
  return (
    <div className="language" role="group" aria-label={t("language")}>
      {LANGUAGES.map((item) => (
        <button
          key={item.code}
          type="button"
          lang={item.code}
          aria-pressed={language === item.code}
          onClick={() => setLanguage(item.code)}
        >
          {item.name}
        </button>
      ))}
    </div>
  );
}
