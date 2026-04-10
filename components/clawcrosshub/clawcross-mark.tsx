import { useId } from "react";

import { cn } from "@/lib/utils";

export function ClawcrossMark({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  const bladeId = `${id}-clawcrossBlade`;
  const nodeId = `${id}-clawcrossNode`;
  const orbitId = `${id}-clawcrossOrbit`;
  const shadowId = `${id}-clawcrossShadow`;

  return (
    <svg
      viewBox="0 0 256 256"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("h-8 w-8 shrink-0", className)}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={bladeId} x1="44" y1="44" x2="214" y2="212" gradientUnits="userSpaceOnUse">
          <stop stopColor="#BCE6FF" />
          <stop offset="0.5" stopColor="#5EA8FF" />
          <stop offset="1" stopColor="#2448D8" />
        </linearGradient>
        <linearGradient id={nodeId} x1="82" y1="116" x2="108" y2="172" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFD7A1" />
          <stop offset="1" stopColor="#FF8A3D" />
        </linearGradient>
        <linearGradient id={orbitId} x1="38" y1="198" x2="188" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1E293B" />
          <stop offset="1" stopColor="#4F46E5" />
        </linearGradient>
        <filter
          id={shadowId}
          x="10"
          y="16"
          width="236"
          height="224"
          filterUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#0F172A" floodOpacity="0.18" />
        </filter>
      </defs>

      <g filter={`url(#${shadowId})`}>
        <path
          d="M58 187C58 137.847 97.8467 98 147 98H170C174.418 98 178 101.582 178 106V126C178 130.418 174.418 134 170 134H145C117.386 134 95 156.386 95 184V190C95 194.418 91.4183 198 87 198H66C61.5817 198 58 194.418 58 190V187Z"
          fill={`url(#${orbitId})`}
        />
        <path d="M55 128C83 97 121 71 196 46C191 72 178 92 158 108C134 126 108 137 74 141L55 128Z" fill={`url(#${bladeId})`} />
        <path d="M49 150C83 131 129 124 214 128C200 147 176 161 146 170C111 180 81 176 58 161L49 150Z" fill={`url(#${bladeId})`} />
        <path d="M58 171C90 181 134 196 196 212C176 226 147 229 116 220C90 212 69 198 58 181V171Z" fill={`url(#${bladeId})`} />

        <circle cx="187" cy="60" r="12" fill="#EFF8FF" />
        <circle cx="206" cy="130" r="12" fill="#EFF8FF" />
        <circle cx="187" cy="205" r="12" fill="#EFF8FF" />
        <circle cx="187" cy="60" r="7" fill="#1F4FD6" />
        <circle cx="206" cy="130" r="7" fill="#1F4FD6" />
        <circle cx="187" cy="205" r="7" fill="#1F4FD6" />

        <path d="M88 122L106 112L124 122V143L106 153L88 143V122Z" fill="#EEF6FF" />
        <path d="M106 112L124 122L106 132L88 122L106 112Z" fill="#D4E8FF" />
        <path d="M106 132L124 122V143L106 153V132Z" fill="#84BCFF" />
        <path d="M88 122L106 132V153L88 143V122Z" fill="#3466F6" />
        <circle cx="106" cy="132" r="18" fill={`url(#${nodeId})`} fillOpacity="0.18" />
        <circle cx="106" cy="132" r="6" fill="#FF9B52" />

        <path d="M96 96C112 78 140 64 174 62" stroke="#D9EEFF" strokeWidth="6" strokeLinecap="round" strokeOpacity="0.7" />
        <path d="M102 132H178" stroke="#D9EEFF" strokeWidth="6" strokeLinecap="round" strokeOpacity="0.7" />
        <path d="M96 167C115 180 142 192 174 198" stroke="#D9EEFF" strokeWidth="6" strokeLinecap="round" strokeOpacity="0.7" />
      </g>
    </svg>
  );
}
