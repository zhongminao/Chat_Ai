import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ExecutionItem, Item } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { MessageContent } from './MessageContent';
import { ToolCallCard } from './ToolCallCard';
import { ReportCard } from './ReportCard';
import type { ImageAsset } from '../../api/types';
import { MessageImages } from '../images/MessageImages';

export function MessageList({ items, busy, loading, assistantId, sessionId, images, onRenameImage, editingImage }: {
  items: Item[]; busy: boolean; loading: boolean; assistantId: string | null;
  sessionId: string | null; images: ImageAsset[]; editingImage: boolean;
  onRenameImage: (id: string, name: string) => Promise<boolean>;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const contentBox = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [away, setAway] = useState(false);
  const bottom = () => {
    const element = viewport.current;
    if (element) { element.scrollTop = element.scrollHeight; follow.current = true; setAway(false); }
  };
  useLayoutEffect(() => { if (follow.current) bottom(); }, [items, busy]);

  const hasItems = items.length > 0;
  useEffect(() => {
    const content = contentBox.current;
    if (!content) return;
    const observer = new ResizeObserver(() => {
      const element = viewport.current;
      if (element && follow.current) element.scrollTop = element.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [loading, hasItems]);

  const renderExecution = (item: ExecutionItem) => item.kind === 'tool'
    ? <ToolCallCard key={item.id} item={item} sessionId={sessionId} images={images} />
    : <article key={item.id} className={`message ${item.role}`} aria-label={item.role === 'user' ? '你的消息' : '助手回复'}>
      {sessionId && item.images?.length ? <MessageImages ids={item.images} assets={images} sessionId={sessionId}
        disabled={busy || editingImage} onRename={onRenameImage} /> : null}
      {item.content && <MessageContent content={item.content} role={item.role} streaming={busy && item.id === assistantId} />}
    </article>;

  return <div className="conversation-area">
    <div ref={viewport} className="message-viewport" role="log" aria-label="对话" aria-busy={loading}
      onScroll={() => {
        const element = viewport.current;
        if (!element) return;
        follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
        setAway(!follow.current);
      }}>
      {loading ? <div className="empty-state"><span className="loading-dot" />加载会话…</div>
        : !items.length ? <div className="empty-state"><div className="welcome-mark"><Icon name="chat" size={26} /></div>
          <h1>开始一段对话</h1><p>发送消息，与 agent 一起处理任务。</p></div>
        : <div ref={contentBox} className="message-list">{items.map(item => item.kind === 'report'
          ? <ReportCard key={item.id} item={item} onInspect={() => { follow.current = false; }}>
            {item.process.map(renderExecution)}
          </ReportCard>
          : renderExecution(item))}
          {busy && <div className="run-indicator" role="status"><span className="loading-dot" />正在执行…</div>}
        </div>}
    </div>
    {away && <button className="scroll-bottom" onClick={bottom}><Icon name="down" size={16} />回到最新消息</button>}
  </div>;
}
