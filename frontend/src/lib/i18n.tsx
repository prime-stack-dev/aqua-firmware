"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { type Language, type MessageKey, MESSAGES } from "./messages";

const STORAGE_KEY = "aqua.language";
const LOCALES: Record<Language, string> = { en: "en-IN", hi: "hi-IN", te: "te-IN" };

export const LANGUAGES: { code: Language; name: string }[] = [
  { code: "en", name: "English" },
  { code: "hi", name: "हिंदी" },
  { code: "te", name: "తెలుగు" },
];

function isLanguage(value: string | null): value is Language {
  return value === "en" || value === "hi" || value === "te";
}

function savedLanguage(): Language | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

function browserLanguage(): Language {
  const code = navigator.language.slice(0, 2);
  return isLanguage(code) ? code : "en";
}

interface I18n {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
  /** A date and time written the way the chosen language writes it. */
  dateTime: (value: string | null | undefined) => string;
  locale: string;
}

const I18nContext = createContext<I18n | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useEffect(() => {
    setLanguageState(savedLanguage() ?? browserLanguage());
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice still applies until the page is closed.
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const locale = LOCALES[language];
    return {
      language,
      setLanguage,
      locale,
      t: (key, values = {}) =>
        Object.entries(values).reduce(
          (text, [name, replacement]) => text.replace(`{${name}}`, String(replacement)),
          MESSAGES[language][key],
        ),
      dateTime: (date) =>
        date
          ? new Date(date).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })
          : "—",
    };
  }, [language, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside LanguageProvider");
  return value;
}
