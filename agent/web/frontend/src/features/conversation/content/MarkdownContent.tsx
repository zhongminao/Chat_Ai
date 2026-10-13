import { createContext, useContext } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlock } from './CodeBlock';
import { MathBlock } from './MathBlock';
import { isMathBlockClosed, remarkBlockMath } from './mathBlocks';
import './content.css';

const SourceContext = createContext('');
const plugins = [remarkGfm, remarkBlockMath];

const components: Components = {
  pre({ node, children, ...props }) {
    const original = useContext(SourceContext);
    const code = node?.children.find(child => child.type === 'element' && child.tagName === 'code');
    if (code?.type !== 'element') return <pre {...props}>{children}</pre>;
    const names = code.properties.className;
    const classes = Array.isArray(names) ? names.map(String) : [];
    const language = classes.find(name => name.startsWith('language-'))?.slice(9) ?? '';
    const text = code.children.map(child => child.type === 'text' ? child.value : '').join('');
    const dollars = classes.includes('math-display');
    // Code fences acquire a presentation newline; math nodes retain exact values.
    const source = !dollars && text.endsWith('\n') ? text.slice(0, -1) : text;
    if (language.toLowerCase() === 'math') {
      const start = node?.position?.start.offset;
      const end = node?.position?.end.offset;
      const raw = start === undefined || end === undefined ? '' : original.slice(start, end);
      return <MathBlock source={source} raw={raw} closed={isMathBlockClosed(raw, dollars ? 'dollars' : 'fence')} />;
    }
    return <CodeBlock code={source} language={language} />;
  },
  table({ node: _node, children, ...props }) {
    return <div className="markdown-table-scroll" tabIndex={0} role="region" aria-label="表格">
      <table {...props}>{children}</table>
    </div>;
  },
  a({ node: _node, children, ...props }) {
    return <a {...props} target="_blank" rel="noopener noreferrer">{children}</a>;
  },
  img({ node: _node, ...props }) {
    return <img {...props} loading="lazy" decoding="async" />;
  },
};

export function MarkdownContent({ content }: { content: string }) {
  return <SourceContext.Provider value={content}><div className="markdown-content">
    <Markdown remarkPlugins={plugins} components={components}>{content}</Markdown>
  </div></SourceContext.Provider>;
}
