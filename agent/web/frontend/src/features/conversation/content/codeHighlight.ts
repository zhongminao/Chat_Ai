import type { HighlighterCore, ThemedToken } from 'shiki/core';

// Each entry produces its own lazy-loaded chunk. No full language bundle.
const languages = {
  python: () => import('@shikijs/langs/python'),
  bash: () => import('@shikijs/langs/bash'),
  javascript: () => import('@shikijs/langs/javascript'),
  typescript: () => import('@shikijs/langs/typescript'),
  jsx: () => import('@shikijs/langs/jsx'),
  tsx: () => import('@shikijs/langs/tsx'),
  json: () => import('@shikijs/langs/json'),
  yaml: () => import('@shikijs/langs/yaml'),
  html: () => import('@shikijs/langs/html'),
  css: () => import('@shikijs/langs/css'),
  sql: () => import('@shikijs/langs/sql'),
  diff: () => import('@shikijs/langs/diff'),
};
type Language = keyof typeof languages;
const aliases: Record<string, Language> = {
  py: 'python', python3: 'python', sh: 'bash', shell: 'bash', zsh: 'bash',
  js: 'javascript', ts: 'typescript', yml: 'yaml', htm: 'html', patch: 'diff',
};
const labels: Record<Language, string> = {
  python: 'Python', bash: 'Bash', javascript: 'JavaScript', typescript: 'TypeScript',
  jsx: 'JSX', tsx: 'TSX', json: 'JSON', yaml: 'YAML', html: 'HTML', css: 'CSS', sql: 'SQL', diff: 'Diff',
};

function resolveLanguage(value: string): Language | null {
  const name = value.toLowerCase();
  return aliases[name] ?? (Object.hasOwn(languages, name) ? name as Language : null);
}

export function languageLabel(value: string): string {
  const language = resolveLanguage(value);
  return language ? labels[language] : value || 'Text';
}

let highlighter: Promise<HighlighterCore> | null = null;
const loadingLanguages = new Map<Language, Promise<void>>();

function getHighlighter(): Promise<HighlighterCore> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createOnigurumaEngine }, theme] = await Promise.all([
      import('shiki/core'), import('shiki/engine/oniguruma'), import('@shikijs/themes/github-light'),
    ]);
    return createHighlighterCore({
      themes: [theme.default], langs: [], engine: createOnigurumaEngine(import('shiki/wasm')),
    });
  })().catch(error => { highlighter = null; throw error; });
  return highlighter;
}

export async function highlightCode(code: string, name: string): Promise<ThemedToken[][] | null> {
  const language = resolveLanguage(name);
  // Preserve large/unknown blocks as text rather than stalling the UI.
  if (!language || code.length > 100_000) return null;
  const engine = await getHighlighter();
  if (!engine.getLoadedLanguages().includes(language)) {
    let pending = loadingLanguages.get(language);
    if (!pending) {
      pending = languages[language]().then(grammar => engine.loadLanguage(grammar.default));
      loadingLanguages.set(language, pending);
    }
    try { await pending; } finally { loadingLanguages.delete(language); }
  }
  return engine.codeToTokens(code, { lang: language, theme: 'github-light' }).tokens;
}
