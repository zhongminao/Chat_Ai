import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ExecutionItem, Item } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { MessageContent } from './MessageContent';
import { ToolCallCard } from './ToolCallCard';
import { ReportCard } from './ReportCard';
import type { ImageAsset } from '../../api/types';
import { MessageImages } from '../images/MessageImages';

export function MessageList({ items, busy, loading, assistantId, sessionId, images, onRenameImage, editingImage, waitingCallIds = [], hasMore = false, loadingMore = false, historyError = null, onLoadMore, revision = 0 }: {
  items: Item[]; busy: boolean; loading: boolean; assistantId: string | null;
  sessionId: string | null; images: ImageAsset[]; editingImage: boolean;
  onRenameImage: (id: string, name: string) => Promise<boolean>;
  waitingCallIds?: string[]; hasMore?: boolean; loadingMore?: boolean; historyError?: string | null;
  onLoadMore?: () => void; revision?: number;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const contentBox = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [away, setAway] = useState(false);
  const anchor = useRef<{ height: number; top: number } | null>(null);
  const moreWasLoading = useRef(false);
  const inspectedTool = useRef<{ summary: HTMLElement; top: number } | null>(null);
  const lastRevision = useRef(revision);
  useLayoutEffect(() => {
    const element = viewport.current;
    const finished = moreWasLoading.current && !loadingMore;
    moreWasLoading.current = loadingMore;
    if (revision !== lastRevision.current) {
      if (anchor.current && element) {
        element.scrollTop = anchor.current.top + element.scrollHeight - anchor.current.height;
        anchor.current = null;
      }
      lastRevision.current = revision;
    } else if (finished) anchor.current = null;
  }, [revision, loadingMore]);
  const inspectTool = (summary: HTMLElement) => {
    const element = viewport.current;
    if (!element) return;
    follow.current = false;
    setAway(true);
    inspectedTool.current = { summary, top: summary.getBoundingClientRect().top };
  };
  // The browser may adjust scrollTop for scroll anchoring as <details> grows. Restore
  // the clicked summary after layout, before paint, without moving it to the bottom.
  const keepInspectedTool = () => {
    const target = inspectedTool.current;
    const element = viewport.current;
    if (!target || !element) return;
    if (!element.contains(target.summary)) { inspectedTool.current = null; return; }
    element.scrollTop += target.summary.getBoundingClientRect().top - target.top;
  };
  const bottom = () => {
    inspectedTool.current = null;
    const element = viewport.current;
    if (element) { element.scrollTop = element.scrollHeight; follow.current = true; setAway(false); }
  };
  useLayoutEffect(() => { if (follow.current && !anchor.current) bottom(); else keepInspectedTool(); }, [items, busy]);

  const hasItems = items.length > 0;
  const compacting = items.some(item => item.kind === 'context' && item.status === 'running');
  const pendingGuidance = items.findIndex(item => item.kind === 'text' && item.guidance === 'queued');
  const progressIndex = pendingGuidance < 0 ? items.length : pendingGuidance;
  const progress = busy && !compacting
    ? <div className="run-indicator" role="status"><span className="loading-dot" />{waitingCallIds.length ? '等待审批…' : '正在执行…'}</div> : null;
  useEffect(() => {
    const content = contentBox.current;
    if (!content) return;
    const observer = new ResizeObserver(() => {
      const element = viewport.current;
      if (element && follow.current && !anchor.current) element.scrollTop = element.scrollHeight;
      else keepInspectedTool();
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [loading, hasItems]);

  const renderExecution = (item: ExecutionItem) => item.kind === 'tool'
    ? <ToolCallCard key={item.id} item={item} onInspect={inspectTool} sessionId={sessionId} images={images} waiting={waitingCallIds.some(id => item.id === `tool:${id}`)} />
    : <article key={item.id} className={`message ${item.role}`} aria-label={item.role === 'user' ? '你的消息' : '助手回复'}>
      {sessionId && item.images?.length ? <MessageImages ids={item.images} assets={images} sessionId={sessionId}
        disabled={busy || editingImage} onRename={onRenameImage} /> : null}
      {item.content && <MessageContent content={item.content} role={item.role} streaming={busy && !loading && item.id === assistantId} />}
    </article>;

  return <div className="conversation-area">
    <div ref={viewport} className="message-viewport" role="log" aria-label="对话" aria-busy={loading}
      onScroll={() => {
        const element = viewport.current;
        if (!element) return;
        if (inspectedTool.current) return;
        follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
        setAway(!follow.current);
      }}>
      {(hasMore || historyError) && !loading && <div className="load-more-history">
        {hasMore && <button disabled={loadingMore} onClick={() => {
          const element = viewport.current;
          if (element) { inspectedTool.current = null; anchor.current = { height: element.scrollHeight, top: element.scrollTop }; follow.current = false; }
          onLoadMore?.();
        }}>{loadingMore ? '正在加载…' : '加载更多历史'}</button>}
        {historyError && <span role="alert">{historyError}</span>}
      </div>}
      {loading && !hasItems ? <div className="empty-state"><span className="loading-dot" />加载会话…</div>
        : !items.length ? <div className="empty-state"><div className="welcome-mark"><Icon name="chat" size={26} /></div>
          <h1>开始一段对话</h1><p>发送消息，与 agent 一起处理任务。</p></div>
        : <div ref={contentBox} className="message-list">{items.map((item, index) => <Fragment key={item.id}>
          {index === progressIndex && progress}
          {item.kind === 'report'
          ? <ReportCard key={item.id} item={item} onInspect={() => { follow.current = false; }}>
            {item.process.map(renderExecution)}
          </ReportCard>
          : item.kind === 'context'
            ? <div key={item.id} className="context-marker" role="status" title={item.reason}>
              {item.status === 'running' ? <span className="loading-dot" /> : <Icon name="compact" size={16} />}
              {({ running: '正在自动压缩上下文', completed: '上下文已自动压缩', failed: '上下文自动压缩失败',
                cancelled: '上下文自动压缩已取消', interrupted: '上下文自动压缩已中断' })[item.status]}
            </div>
            : renderExecution(item)}
        </Fragment>)}
          {progressIndex === items.length && progress}
        </div>}
    </div>
    {away && <button className="scroll-bottom" onClick={bottom}><Icon name="down" size={16} />回到最新消息</button>}
  </div>;
}
