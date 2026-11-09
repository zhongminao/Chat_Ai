import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ImageAttachments } from './ImageAttachments';

const image = { id: 'image', name: '原文件.png', filename: '原文件.png', ordinal: 1,
  mime: 'image/png', width: 160, height: 110, size: 100 };
describe('read-only image labels', () => {
  it('keeps preview and original label without rename controls', () => {
    const html = renderToStaticMarkup(<ImageAttachments sessionId="session" images={[image]} />);
    expect(html).toContain('1 / 原文件.png');
    expect(html).toContain('/images/image/content');
    expect(html).not.toContain('image-info');
    expect(html).not.toContain('160 × 110');
    expect(html).not.toContain('<input');
    expect(html).not.toContain('<button');
  });
  it('uses object URLs only for local null-session previews, without API URLs', () => {
    const html = renderToStaticMarkup(<ImageAttachments sessionId={null} images={[image]}
      previewUrls={new Map([[image.id, 'blob:local-preview']])} onRemove={vi.fn()} />);
    expect(html).toContain('href="blob:local-preview"');
    expect(html).toContain('src="blob:local-preview"');
    expect(html).toContain('移除图片');
    expect(html).not.toContain('/api/');
  });
  it('retains the remove action for uploaded drafts', () => {
    const html = renderToStaticMarkup(<ImageAttachments sessionId="session" images={[image]} onRemove={vi.fn()} />);
    expect(html).toContain('移除图片');
    expect(html).not.toContain('<input');
  });
});
