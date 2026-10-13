import { memo, useEffect, useState } from 'react';
import { CodeBlock } from './CodeBlock';
import 'katex/dist/katex.min.css';

async function importKatex() {
  const module = await import('katex');
  return module.default;
}
let library: ReturnType<typeof importKatex> | null = null;
function getKatex() {
  library ??= importKatex().catch(error => { library = null; throw error; });
  return library;
}

export const MathBlock = memo(function MathBlock({ source, raw, closed }: {
  source: string; raw: string; closed: boolean;
}) {
  const [rendered, setRendered] = useState<{ source: string; html: string | null } | null>(null);
  useEffect(() => {
    if (!closed || !source.trim()) return;
    let active = true;
    getKatex().then(katex => {
      // A fresh macro scope keeps definitions local to this formula.
      const html = katex.renderToString(source, {
        displayMode: true,
        output: 'htmlAndMathml',
        throwOnError: true,
        trust: false,
        strict: 'ignore',
        macros: {},
        maxExpand: 1000,
        maxSize: 10,
      });
      if (active) setRendered({ source, html });
    }).catch(() => { if (active) setRendered({ source, html: null }); });
    return () => { active = false; };
  }, [source, closed]);

  const current = rendered?.source === source ? rendered : null;
  if (!closed || !current?.html) {
    return <div className="math-source-block">
      <div className="math-source-label">{!closed ? '公式源码 · 尚未闭合'
        : current?.html === null ? '公式无法排版 · 已保留源码' : '公式源码'}</div>
      <CodeBlock code={raw || source} language="latex" />
    </div>;
  }
  return <div className="math-block">
    {/* Only KaTeX-generated markup is inserted; raw message HTML is never used. */}
    <div className="math-formula" tabIndex={0} role="region" aria-label="数学公式"
      dangerouslySetInnerHTML={{ __html: current.html }} />
    <details className="math-source-details">
      <summary>LaTeX 源码</summary>
      <CodeBlock code={source} language="latex" />
    </details>
  </div>;
});
