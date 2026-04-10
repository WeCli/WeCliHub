"use client";

import type { CSSProperties, ElementType, HTMLAttributes } from "react";
import { startTransition, useDeferredValue, useEffect, useLayoutEffect, useMemo, useState } from "react";

import { layoutWithLines } from "@chenglou/pretext";
import type { PreparedTextWithSegments } from "@chenglou/pretext";

import { useI18n } from "@/lib/i18n";
import {
  findBalancedWidth,
  fitTextWithEllipsis,
  getFontFromStyles,
  getPreparedSegments,
  parseLineHeight,
  syncPretextLocale
} from "@/lib/pretext-layout";
import { cn } from "@/lib/utils";

type PretextTextProps = Omit<HTMLAttributes<HTMLElement>, "children"> & {
  as?: ElementType;
  text: string;
  lineClassName?: string;
  maxLines?: number;
  reserveLines?: number;
  balance?: boolean;
  idealLineCount?: number;
  balanceMinRatio?: number;
  titleWhenTruncated?: boolean;
};

type TextMetrics = {
  font: string;
  lineHeight: number;
  width: number;
};

type DisplayLines = {
  lines: string[];
  truncated: boolean;
  width: number;
};

const useIsomorphicLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

function clampDisplayLines(
  prepared: PreparedTextWithSegments,
  width: number,
  lineHeight: number,
  font: string,
  maxLines?: number
): DisplayLines {
  const result = layoutWithLines(prepared, width, lineHeight);
  const lines = result.lines.map((line) => line.text);

  if (!maxLines || lines.length <= maxLines) {
    return { lines, truncated: false, width };
  }

  const visibleLines = lines.slice(0, maxLines);
  visibleLines[maxLines - 1] = fitTextWithEllipsis(visibleLines[maxLines - 1] ?? "", width, font, lineHeight);
  return { lines: visibleLines, truncated: true, width };
}

export function PretextText({
  as,
  balance = false,
  balanceMinRatio,
  className,
  idealLineCount,
  lineClassName,
  maxLines,
  reserveLines,
  style,
  text,
  title,
  titleWhenTruncated = true,
  ...props
}: PretextTextProps) {
  const Component = (as ?? "div") as ElementType;
  const { locale } = useI18n();
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [metrics, setMetrics] = useState<TextMetrics | null>(null);
  const [fontsReady, setFontsReady] = useState(false);

  useEffect(() => {
    syncPretextLocale(locale);
  }, [locale]);

  useEffect(() => {
    let active = true;

    if (typeof document === "undefined") {
      setFontsReady(true);
      return () => {
        active = false;
      };
    }

    const readyPromise = document.fonts?.ready;
    if (!readyPromise) {
      setFontsReady(true);
      return () => {
        active = false;
      };
    }

    readyPromise.then(() => {
      if (active) {
        setFontsReady(true);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  useIsomorphicLayoutEffect(() => {
    if (!node) {
      return;
    }

    let frame = 0;
    const readMetrics = () => {
      const styles = window.getComputedStyle(node);
      const nextMetrics = {
        font: getFontFromStyles(styles),
        lineHeight: parseLineHeight(styles),
        width: Math.max(Math.floor(node.clientWidth), 1)
      };

      startTransition(() => {
        setMetrics((previous) => {
          if (
            previous &&
            previous.font === nextMetrics.font &&
            previous.lineHeight === nextMetrics.lineHeight &&
            previous.width === nextMetrics.width
          ) {
            return previous;
          }
          return nextMetrics;
        });
      });
    };

    const scheduleRead = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(readMetrics);
    };

    readMetrics();

    const observer = new ResizeObserver(scheduleRead);
    observer.observe(node);

    document.fonts?.ready.then(scheduleRead).catch(() => {
      // no-op
    });

    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, [node]);

  const deferredMetrics = useDeferredValue(metrics);
  const prepared = useMemo(() => {
    if (!fontsReady || !deferredMetrics || !text) {
      return null;
    }

    return getPreparedSegments(text, deferredMetrics.font);
  }, [deferredMetrics, fontsReady, text]);

  const display = useMemo(() => {
    if (!prepared || !deferredMetrics) {
      return null;
    }

    const resolvedWidth = balance
      ? findBalancedWidth(prepared, deferredMetrics.width, deferredMetrics.lineHeight, idealLineCount, balanceMinRatio)
      : deferredMetrics.width;

    return clampDisplayLines(
      prepared,
      resolvedWidth,
      deferredMetrics.lineHeight,
      deferredMetrics.font,
      maxLines
    );
  }, [balance, balanceMinRatio, deferredMetrics, idealLineCount, maxLines, prepared]);

  const resolvedTitle = title ?? (display?.truncated && titleWhenTruncated ? text : undefined);
  const resolvedStyle: CSSProperties | undefined =
    reserveLines && deferredMetrics
      ? {
          ...style,
          minHeight: `${deferredMetrics.lineHeight * reserveLines}px`,
          ...(balance && display ? { maxWidth: `${Math.ceil(display.width)}px` } : {})
        }
      : balance && display
        ? {
            ...style,
            maxWidth: `${Math.ceil(display.width)}px`
          }
        : style;

  return (
    <Component
      {...props}
      ref={setNode}
      className={className}
      style={resolvedStyle}
      title={resolvedTitle}
      aria-label={display ? text : undefined}
    >
      {display
        ? (
            <>
              <span className="sr-only">{text}</span>
              <span aria-hidden="true" className="block">
                {display.lines.map((line, index) => (
                  <span key={`${index}-${line}`} className={cn("block", lineClassName)}>
                    {line}
                  </span>
                ))}
              </span>
            </>
          )
        : text}
    </Component>
  );
}
