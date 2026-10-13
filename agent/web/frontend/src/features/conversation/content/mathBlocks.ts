import type { Plugin } from 'unified';
import { math } from 'micromark-extension-math';
import { mathFromMarkdown } from 'mdast-util-math';

// Register only the block grammar. Neither $...$ nor inline $$...$$ becomes math.
export const remarkBlockMath: Plugin = function () {
  const data = this.data() as {
    micromarkExtensions?: ReturnType<typeof math>[];
    fromMarkdownExtensions?: ReturnType<typeof mathFromMarkdown>[];
  };
  const syntax = math();
  (data.micromarkExtensions ??= []).push({ flow: syntax.flow });
  (data.fromMarkdownExtensions ??= []).push(mathFromMarkdown());
};

/** Markdown accepts unfinished fences; display math only after a real closer. */
export function isMathBlockClosed(raw: string, kind: 'dollars' | 'fence'): boolean {
  const lines = raw.replace(/\r\n?/g, '\n').trimEnd().split('\n');
  if (lines.length < 2) return false;
  const opening = lines[0].trim();
  // Later lines can retain a surrounding quote/list prefix in source positions.
  const closing = lines.at(-1)!.replace(/^[\t >]*/, '').trimEnd();
  if (kind === 'dollars') {
    return /^\${2,}$/.test(opening) && /^\${2,}$/.test(closing) && closing.length >= opening.length;
  }
  const fence = opening.match(/^(`{3,}|~{3,})/);
  return Boolean(fence && closing.length >= fence[1].length &&
    [...closing].every(character => character === fence[1][0]));
}
