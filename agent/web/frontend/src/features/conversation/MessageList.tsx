import { Fragment, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { Item, ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { MessageContent } from './MessageContent';
import { ExecutionSteps } from './ExecutionSteps';
import { ReportCard } from './ReportCard';
import type { ImageAsset } from '../../api/types';
import { MessageImages } from '../images/MessageImages';
import type { DisclosureState } from './toolPresentation';

export function MessageList({ footer, items, busy, loading, assistantId, sessionId, images, waitingCallIds = [], hasMore = false, loadingMore = false, historyError = null, onLoadMore, revision = 0 }: {
  footer?: ReactNode;
  items: Item[]; busy: boolean; loading: boolean; assistantId: string | null;
  sessionId: string | null; images: ImageAsset[];
  waitingCallIds?: string[]; hasMore?: boolean; loadingMore?: boolean; historyError?: string | null;
  onLoadMore?: () => void; revision?: number;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const contentBox = useRef<HTMLDivElement>(null);
  const footerBox = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [away, setAway] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const anchor = useRef<{ height: number; top: number } | null>(null);
  const moreWasLoading = useRef(false);
  const lastRevision = useRef(revision);
  const autoHistory = useRef({ pages: 0, revision: -1 });
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
  // Expanding details pauses following, but must not pin the clicked title:
  // overflow-anchor: none keeps the viewport stable while new content arrives.
  const pauseFollowing = () => {
    autoHistory.current.pages = 3;
    follow.current = false;
    setAway(true);
  };
  const bottom = () => {
    const element = viewport.current;
    if (element) { element.scrollTop = element.scrollHeight; follow.current = true; setAway(false); }
  };
  useLayoutEffect(() => { if (follow.current && !anchor.current) bottom(); }, [items, busy]);

  const hasItems = items.length > 0;
  const compacting = items.some(item => item.kind === 'context' && item.status === 'running');
  const pendingGuidance = items.findIndex(item => item.kind === 'text' && item.guidance === 'queued');
  const progressIndex = pendingGuidance < 0 ? items.length : pendingGuidance;
  const progress = busy && !compacting
    ? <div className="run-indicator" role="status"><span className="loading-dot" />{waitingCallIds.length ? '等待审批…' : '正在执行…'}</div> : null;
  useEffect(() => {
    const content = contentBox.current;
    if (!content) return;
    const measure = () => {
      const element = viewport.current;
      const footerElement = footerBox.current;
      if (element && footerElement) {
        const limit = element.clientHeight * 0.65;
        footerElement.style.setProperty('--composer-height-limit', `${limit}px`);
        footerElement.classList.toggle('is-tall', Boolean(footerElement.firstElementChild && footerElement.firstElementChild.scrollHeight > limit));
      }
      if (element && follow.current && !anchor.current) {
        element.scrollTop = element.scrollHeight;
        if (!loading && !loadingMore && !historyError && hasMore && onLoadMore
            && autoHistory.current.pages < 3 && autoHistory.current.revision !== revision
            && element.scrollHeight <= element.clientHeight + 2) {
          autoHistory.current = { pages: autoHistory.current.pages + 1, revision };
          onLoadMore();
        }
      }
    };
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    if (viewport.current) observer.observe(viewport.current);
    if (footerBox.current?.firstElementChild) observer.observe(footerBox.current.firstElementChild);
    measure();
    return () => observer.disconnect();
  }, [loading, hasItems, loadingMore, historyError, hasMore, revision, onLoadMore]);

  const disclosures: DisclosureState = {
    isOpen: (id, fallback = false) => expanded[id] ?? fallback,
    toggle: (id, fallback = false) => {
      if (!(expanded[id] ?? fallback)) pauseFollowing();
      setExpanded(previous => ({ ...previous, [id]: !(previous[id] ?? fallback) }));
    },
  };
  const renderExecutionAt = (source: Item[], index: number) => {
    const item = source[index];
    if (item.kind === 'context' || item.kind === 'report') return null;
    if (item.kind === 'text') return <article key={item.id} className={`message ${item.role}`}
      aria-label={item.role === 'user' ? '你的消息' : '助手回复'}>
      {sessionId && item.images?.length ? <MessageImages ids={item.images} assets={images} sessionId={sessionId} /> : null}
      {item.content && <MessageContent content={item.content} role={item.role} streaming={busy && !loading && item.id === assistantId} />}
    </article>;
    if (index > 0 && source[index - 1].kind === 'tool') return null;
    const tools: ToolItem[] = [];
    for (let cursor = index; cursor < source.length && source[cursor].kind === 'tool'; cursor++) {
      tools.push(source[cursor] as ToolItem);
    }
    return <ExecutionSteps key={`steps:${item.id}`} items={tools} disclosures={disclosures}
      sessionId={sessionId} images={images} waitingCallIds={waitingCallIds} />;
  };

  return <div className="conversation-area">
    <div ref={viewport} className="message-viewport"
      onScroll={() => {
        const element = viewport.current;
        if (!element) return;
        follow.current = element.scrollHeight - element.scrollTop - element.clientHeight <= 2;
        if (!follow.current) autoHistory.current.pages = 3;
        setAway(!follow.current);
      }}>
      <div ref={contentBox} className="message-body">
      <div className="message-thread" role="log" aria-label="对话" aria-busy={loading}>
        {(hasMore || historyError) && !loading && <div className="load-more-history">
          {hasMore && <button disabled={loadingMore} onClick={() => {
            autoHistory.current.pages = 3;
            const element = viewport.current;
            if (element) { anchor.current = { height: element.scrollHeight, top: element.scrollTop }; follow.current = false; }
            onLoadMore?.();
          }}>{loadingMore ? '正在加载…' : '加载更多历史'}</button>}
          {historyError && <span role="alert">{historyError}</span>}
        </div>}
        {loading && !hasItems ? <div className="empty-state"><span className="loading-dot" />加载会话…</div>
          : !items.length ? <div className="empty-state"><div className="welcome-mark"><Icon name="chat" size={26} /></div>
            <h1>开始一段对话</h1><p>发送消息，与 agent 一起处理任务。</p></div>
          : <div className="message-list">{items.map((item, index) => <Fragment key={item.id}>
            {index === progressIndex && progress}
            {item.kind === 'report'
            ? <ReportCard key={item.id} item={item} disclosures={disclosures}>
              {item.process.map((_, index) => renderExecutionAt(item.process, index))}
            </ReportCard>
            : item.kind === 'context'
              ? <div key={item.id} className={`context-marker ${item.status}`} role="status" title={item.reason}>
                <Icon name="compact" size={16} />
                {({ running: '正在自动压缩上下文', completed: '上下文已自动压缩', failed: '上下文自动压缩失败',
                  cancelled: '上下文自动压缩已取消', interrupted: '上下文自动压缩已中断' })[item.status]}
              </div>
              : renderExecutionAt(items, index)}
          </Fragment>)}
            {progressIndex === items.length && progress}
          </div>}
      </div>
      <div ref={footerBox} className="workspace-bottom">
        {footer}
        {away && <button className="scroll-bottom" onClick={bottom}><Icon name="down" size={16} />回到最新消息</button>}
      </div>
      </div>
    </div>
  </div>;
}
