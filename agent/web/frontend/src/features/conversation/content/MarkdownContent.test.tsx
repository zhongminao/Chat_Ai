import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MarkdownContent } from './MarkdownContent';

describe('report image references', () => {
  it('renders a child-session image URL and hides local image-file metadata', () => {
    const html = renderToStaticMarkup(<MarkdownContent content={
      '![四视图](/api/sessions/child/images/image/content)\n\n<!-- image_file: /private/local.png -->'
    } />);
    expect(html).toContain('src="/api/sessions/child/images/image/content"');
    expect(html).toContain('alt="四视图"');
    expect(html).not.toContain('image_file');
    expect(html).not.toContain('/private/local.png');
  });
});
