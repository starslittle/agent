import type { SVGProps } from "react";

interface QidianMarkProps extends SVGProps<SVGSVGElement> {
  title?: string;
}

export function QidianMark({ title, ...props }: QidianMarkProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title && <title>{title}</title>}
      <circle cx="9" cy="24" r="5" fill="hsl(var(--brand-coral))" />
      <path
        d="M14 24h22"
        stroke="hsl(var(--primary))"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle
        cx="39"
        cy="24"
        r="6"
        fill="hsl(var(--background))"
        stroke="hsl(var(--primary))"
        strokeWidth="3"
      />
    </svg>
  );
}

export function QidianWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <QidianMark className="h-9 w-9 shrink-0" />
      {!compact && (
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold tracking-[-0.02em] text-foreground">
            启点
          </p>
          <p className="truncate text-[9px] font-medium tracking-[0.16em] text-muted-foreground">
            QIDIAN WORKSPACE
          </p>
        </div>
      )}
    </div>
  );
}
