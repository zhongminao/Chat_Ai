import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ContextMeter } from './ContextMeter';

describe('context occupancy ring', () => {
  it('uses the compaction threshold and labels estimated measurements', () => {
    const html = renderToStaticMarkup(<ContextMeter usage={{ usedTokens: 1280, limitTokens: 128000, estimated: true }} />);
    expect(html).toContain('上下文已用约 1%');
    expect(html).toContain('stroke-dasharray="1 100"');
  });
  it('clamps the ring without hiding an over-threshold reading', () => {
    const html = renderToStaticMarkup(<ContextMeter usage={{ usedTokens: 150, limitTokens: 100, estimated: false }} />);
    expect(html).toContain('上下文已用 150%');
    expect(html).toContain('stroke-dasharray="100 100"');
  });
  it('does not invent occupancy for missing or invalid measurements', () => {
    for (const usage of [null, { usedTokens: 1, limitTokens: 0, estimated: true }]) {
      expect(renderToStaticMarkup(<ContextMeter usage={usage} />)).toBe('');
    }
  });
});
