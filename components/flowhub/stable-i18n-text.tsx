"use client";

import { cn } from "@/lib/utils";
import { getTranslation, type Locale, useI18n } from "@/lib/i18n";

const SUPPORTED_LOCALES: Locale[] = ["en", "zh"];

export function StableI18nText({ translationKey, className }: { translationKey: string; className?: string }) {
  const { locale } = useI18n();

  return (
    <span className={cn("inline-grid items-center", className)}>
      {SUPPORTED_LOCALES.map((candidate) => (
        <span
          key={candidate}
          aria-hidden={candidate !== locale}
          className={cn("col-start-1 row-start-1 whitespace-nowrap", candidate === locale ? "visible" : "invisible")}
        >
          {getTranslation(translationKey, candidate)}
        </span>
      ))}
    </span>
  );
}
