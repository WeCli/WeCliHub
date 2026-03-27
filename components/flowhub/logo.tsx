import { cn } from "@/lib/utils";

export function FlowhubLogo({
  className,
  showText = true,
  textClassName
}: {
  className?: string;
  iconClassName?: string;
  showText?: boolean;
  textClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-2xl font-bold", className)}>
      <span className="text-3xl">🌊</span>
      {showText ? (
        <span
          className={cn(
            "flowhub-logo-text",
            textClassName
          )}
        >
          Teamclaw Hub
        </span>
      ) : null}
    </span>
  );
}
