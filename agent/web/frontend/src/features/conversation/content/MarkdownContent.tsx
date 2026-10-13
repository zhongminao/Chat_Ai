import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CodeBlock } from './CodeBlock';
import './content.css';

const components: Components = {
  pre({ node, children, ...props }) {
    const code = node?.children.find(child => child.type === 'element' && child.tagName === 'code');
    if (code?.type !== 'element') return <pre {...props}>{children}</pre>;
    const names = code.properties.className;
    const language = (Array.isArray(names) ? names.map(String) : []).find(name => name.startsWith('language-'))?.slice(9) ?? '';
    const text = code.children.map(child => child.type === 'text' ? child.value : '').join('');
    // remark-rehype appends one presentation newline; keep all source whitespace.
    const source = text.endsWith('\n') ? text.slice(0, -1) : text;
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
  return <div className="markdown-content">
    <Markdown remarkPlugins={[remarkGfm]} components={components}>{content}</Markdown>
  </div>;
}
