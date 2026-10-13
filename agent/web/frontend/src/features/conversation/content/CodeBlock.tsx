import { Fragment, memo, useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import type { ThemedToken } from 'shiki/core';
import { highlightCode, languageLabel } from './codeHighlight';

async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch { /* HTTP deployments may need the browser's legacy copy action. */ }
  const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange()) : [];
  const area = document.createElement('textarea');
  area.value = value;
  area.readOnly = true;
  area.tabIndex = -1;
  area.setAttribute('aria-hidden', 'true');
  area.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none';
  try {
    document.body.append(area);
    area.focus({ preventScroll: true }); area.select(); area.setSelectionRange(0, value.length);
    return document.execCommand('copy');
  } catch { return false; }
  finally {
    area.remove(); active?.focus({ preventScroll: true });
    if (selection) { selection.removeAllRanges(); ranges.forEach(range => selection.addRange(range)); }
  }
}

function tokenStyle(token: ThemedToken): CSSProperties {
  const flags = token.fontStyle ?? 0;
  return {
    color: token.color,
    fontStyle: flags & 1 ? 'italic' : undefined,
    fontWeight: flags & 2 ? 600 : undefined,
    textDecoration: flags & 4 ? 'underline' : undefined,
  };
}

export const CodeBlock = memo(function CodeBlock({ code, language = '' }: { code: string; language?: string }) {
  const [highlight, setHighlight] = useState<{ code: string; language: string; tokens: ThemedToken[][] } | null>(null);
  const [copied, setCopied] = useState<'idle' | 'done' | 'failed'>('idle');
  const copyTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (copyTimer.current) clearTimeout(copyTimer.current); };
  }, []);

  useEffect(() => {
    let active = true;
    // Allow streaming text to settle before tokenizing it.
    const timer = setTimeout(() => {
      highlightCode(code, language).then(tokens => {
        if (active) setHighlight(tokens ? { code, language, tokens } : null);
      }).catch(() => { if (active) setHighlight(null); });
    }, 150);
    return () => { active = false; clearTimeout(timer); };
  }, [code, language]);

  async function copy() {
    const success = await copyText(code);
    if (!mounted.current) return;
    setCopied(success ? 'done' : 'failed');
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied('idle'), 1400);
  }

  const tokens = highlight?.code === code && highlight.language === language ? highlight.tokens : null;
  return <div className="code-block">
    <div className="code-block-toolbar">
      <span className="code-block-language">{languageLabel(language)}</span>
      <button type="button" className="code-block-copy" onClick={() => { void copy(); }} disabled={!code}
        aria-label="复制代码"><span aria-live="polite">{copied === 'done' ? '已复制' : copied === 'failed' ? '复制失败' : '复制'}</span></button>
    </div>
    <pre className="code-block-body" tabIndex={0} aria-label={`${languageLabel(language)} 代码`}><code>
      {tokens ? tokens.map((line, index) => <Fragment key={index}>
        {index > 0 ? '\n' : null}{line.map((token, column) => <span key={column} style={tokenStyle(token)}>{token.content}</span>)}
      </Fragment>) : code}
    </code></pre>
  </div>;
});
