"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { getTranslation, type Locale, useI18n } from "@/lib/i18n";
import { getFontFromStyles, measureSingleLineWidth, syncPretextLocale } from "@/lib/pretext-layout";

const SUPPORTED_LOCALES: Locale[] = ["en", "zh"];

export function StableI18nText({ translationKey, className }: { translationKey: string; className?: string }) {
  const { locale } = useI18n();
  const label = useMemo(() => getTranslation(translationKey, locale), [locale, translationKey]);
  const nodeRef = useRef<HTMLSpanElement | null>(null);
  const [minWidth, setMinWidth] = useState<number>();

  useEffect(() => {
    syncPretextLocale(locale);
  }, [locale]);

  useEffect(() => {
    const element = nodeRef.current;
    if (!element) {
      return;
    }

    let frame = 0;

    const measure = () => {
      const styles = getComputedStyle(element);
      const font = getFontFromStyles(styles);
      const widest = SUPPORTED_LOCALES.reduce((maxWidth, candidate) => {
        const width = measureSingleLineWidth(getTranslation(translationKey, candidate), font);
        return Math.max(maxWidth, width);
      }, 0);

      setMinWidth(Math.ceil(widest));
    };

    const schedule = () => {
      if (frame) {
        cancelAnimationFrame(frame);
      }
      frame = requestAnimationFrame(measure);
    };

    const rerun = () => {
      schedule();
    };

    schedule();
    window.addEventListener("resize", rerun);

    const fonts = document.fonts;
    fonts?.ready.then(rerun).catch(() => {
      // no-op
    });
    fonts?.addEventListener?.("loadingdone", rerun);

    return () => {
      window.removeEventListener("resize", rerun);
      fonts?.removeEventListener?.("loadingdone", rerun);
      if (frame) {
        cancelAnimationFrame(frame);
      }
    };
  }, [locale, translationKey]);

  return (
    <span
      ref={nodeRef}
      className={cn("inline-flex items-center whitespace-nowrap", className)}
      style={minWidth ? { minWidth } : undefined}
    >
      {label}
    </span>
  );
}
