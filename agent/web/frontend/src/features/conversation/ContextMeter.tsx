import type { ContextUsage } from '../../api/types';
import './contextMeter.css';

export function ContextMeter({ usage }: { usage?: ContextUsage | null }) {
  if (!usage || !Number.isFinite(usage.usedTokens) || usage.usedTokens < 0 ||
      !Number.isFinite(usage.limitTokens) || usage.limitTokens <= 0) return null;
  const percent = Math.round(usage.usedTokens / usage.limitTokens * 100);
  const label = `上下文已用${usage.estimated ? '约 ' : ' '}${percent}%`;
  return <span className="context-meter" tabIndex={0} aria-label={label}
    style={{ color: percent >= 100 ? '#b54a43' : percent >= 80 ? '#b08735' : undefined }}>
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" strokeWidth="2">
      <circle cx="7" cy="7" r="5" stroke="currentColor" opacity=".2" />
      <circle cx="7" cy="7" r="5" stroke="currentColor" pathLength="100"
        strokeDasharray={`${Math.min(percent, 100)} 100`} transform="rotate(-90 7 7)" />
    </svg>
    <span className="context-meter-tooltip" role="tooltip">{label}</span>
  </span>;
}
