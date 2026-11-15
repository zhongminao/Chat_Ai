import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ToolImagePreview } from './ToolImagePreview';
import { ToolCallCard } from '../conversation/ToolCallCard';
import { conversationReducer as reduce, emptyConversation, type ToolItem } from '../../state/conversation';
import type { AgentEvent } from '../../api/types';

const image = { id: 'image', name: '测试.png', filename: '测试.png', ordinal: 1,
  mime: 'image/png', width: 1200, height: 900, size: 100 };
const original = '/api/sessions/session/images/image/content';
const disclosures = { isOpen: () => false, toggle: () => {} };
const renderTool = (name: string) => renderToStaticMarkup(<ToolCallCard item={{
  id: 'tool:1', kind: 'tool', name, status: 'completed', readImageIds: ['image'], result: 'saved',
} satisfies ToolItem} sessionId="session" images={[image]} disclosures={disclosures} />);

describe('tool image thumbnails', () => {
  it('loads the saved preview and links to the original in a new tab', () => {
    const html = renderToStaticMarkup(<ToolImagePreview ids={['image']} assets={[image]} sessionId="session" />);
    expect(html).toContain('tool-image-previews');
    expect(html).toContain(`src="${original}?preview=true"`);
    expect(html).toContain(`href="${original}" target="_blank" rel="noopener noreferrer"`);
    expect(html).not.toContain(`src="${original}"`);
    expect(html).toContain('查看原图');
    expect(html).toContain('下载');
  });

  it('keeps read_image previews inside the collapsed tool details', () => {
    const html = renderTool('read_image');
    expect(html).not.toMatch(/<details class="tool-card" open/);
    expect(html.indexOf('tool-image-previews')).toBeLessThan(html.indexOf('</details>'));
    expect(html.match(/<img /g)).toHaveLength(1);
  });

  it('does not automatically display images for other tools', () => {
    const html = renderTool('mcp_image_generation');
    expect(html).not.toContain('tool-image-previews');
    expect(html).not.toContain('<img');
  });

  it('omits unknown images instead of constructing guessed URLs', () => {
    expect(renderToStaticMarkup(<ToolImagePreview ids={['missing']} assets={[image]} sessionId="session" />)).toBe('');
  });
});

describe('read_image event to rendered thumbnail', () => {
  const events: AgentEvent[] = [
    { seq: 1, type: 'tool.requested', tool: 'read_image', callId: 'read', arguments: { path: '/example.png' } },
    { seq: 2, type: 'tool.completed', tool: 'read_image', callId: 'read', result: 'session_path: /example.png',
      model_images: [image] },
  ];
  for (const source of ['live', 'history'] as const) {
    it(`renders model_images from ${source} without a display-images field`, () => {
      const state = reduce(emptyConversation(), source === 'live'
        ? { type: 'events', events }
        : { type: 'history', page: { events, snapshot_seq: 2, min_seq: 1, has_more: false } });
      const tool = state.items[0] as ToolItem;
      expect(tool.readImageIds).toEqual(['image']);
      expect(state.images).toEqual([image]);
      const html = renderToStaticMarkup(<ToolCallCard item={tool} sessionId="session"
        images={state.images} disclosures={{ ...disclosures, isOpen: () => true }} />);
      expect(html).toContain(`src="${original}?preview=true"`);
      expect(html.indexOf('tool-image-previews')).toBeLessThan(html.indexOf('</details>'));
    });
  }
  it('does not expose model-only images on unrelated tools', () => {
    const state = reduce(emptyConversation(), { type: 'events', events: [
      { ...events[1], tool: 'other' } as AgentEvent,
    ] });
    expect((state.items[0] as ToolItem).readImageIds).toEqual([]);
    expect(state.images).toEqual([]);
  });
});
