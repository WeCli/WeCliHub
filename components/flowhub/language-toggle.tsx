"use client";

import { Globe } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();
  const label = locale === "en" ? t("lang.switchToChinese") : t("lang.switchToEnglish");

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-9 w-9"
      onClick={() => setLocale(locale === "en" ? "zh" : "en")}
      title={label}
      aria-label={label}
    >
      <Globe className="h-4 w-4" />
      <span className="sr-only">{label}</span>
    </Button>
  );
}
