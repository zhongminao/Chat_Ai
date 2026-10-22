import { useState } from 'react';
import { useChatLayout } from './useChatLayout';
import { useSessions } from '../features/sessions/useSessions';
import { SessionSidebar } from '../features/sessions/SessionSidebar';
import { useConversation } from '../features/conversation/useConversation';
import { MessageList } from '../features/conversation/MessageList';
import { Composer } from '../features/conversation/Composer';
import { Icon } from '../ui/Icon';
import { WatchStatus } from '../features/watch/WatchStatus';
import { AgentTabs } from '../features/sessions/AgentTabs';
import { useApprovals } from '../features/approvals/useApprovals';
import { ApprovalPanel } from '../features/approvals/ApprovalPanel';

export function App() {
  const sessions = useSessions();
  const layout = useChatLayout(sessions.selected);
  const approvals = useApprovals(sessions.selected);
  const conversation = useConversation(sessions.selected, () => { void sessions.refresh(); });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const current = sessions.sessions.find(item => item.id === sessions.selected);
  const readOnly = Boolean(current?.parent_session_id || conversation.session?.parent_session_id);
  const error = sessions.error || conversation.error || approvals.error;
  const waitingCallIds = (approvals.snapshot?.pending ?? []).filter(item => item.sessionId === sessions.selected).map(item => item.callId);
  const status = sessions.loading ? '正在加载' : !sessions.selected ? '未选择会话'
    : !conversation.connected ? '正在连接' : !conversation.ready ? '正在恢复会话'
    : waitingCallIds.length ? '等待审批' : '已连接';

  return <div className="app-layout">
    <SessionSidebar sessions={sessions.sessions} selected={sessions.selected} loading={sessions.loading}
      creating={sessions.creating} deleting={sessions.deleting} busy={conversation.busy} open={sidebarOpen}
      renaming={sessions.renaming} onRename={sessions.rename}
      onClose={() => setSidebarOpen(false)} onSelect={id => { sessions.select(id); setSidebarOpen(false); }}
      onCreate={() => { void sessions.create(); setSidebarOpen(false); }} onDelete={id => { void sessions.remove(id); }} />
    <main ref={layout.workspace} className="workspace">
      <div ref={layout.top} className="workspace-top">
        <header className="workspace-header">
          <button className="icon-button mobile-only" aria-label="打开会话列表" onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button>
          <AgentTabs sessions={sessions.sessions} selected={sessions.selected} onSelect={sessions.select}>
            <WatchStatus sessionId={current?.parent_session_id ?? sessions.selected}
              onChange={() => { void sessions.refresh(); }} />
          </AgentTabs>
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span>
          {conversation.error && !conversation.ready && <button onClick={conversation.retryHistory}>重新打开会话</button>}
          {!sessions.selected && <button onClick={sessions.retry}>重试</button>}
          {sessions.error && sessions.selected && <button className="icon-button" aria-label="关闭错误提示" onClick={sessions.clearError}><Icon name="close" size={16} /></button>}
        </div>}
      </div>
      <MessageList scrollRef={layout.viewport} key={`messages:${sessions.selected ?? 'empty'}`} items={conversation.items} busy={conversation.busy} assistantId={conversation.assistantId}
        waitingCallIds={waitingCallIds} hasMore={conversation.hasMore} loadingMore={conversation.loadingMore}
        historyError={conversation.historyError} onLoadMore={() => { void conversation.loadMore(); }} revision={conversation.revision}
        sessionId={sessions.selected} images={conversation.images} editingImage={Boolean(conversation.pending)} onRenameImage={conversation.renameImage}
        loading={sessions.loading || Boolean(sessions.selected && !conversation.ready && !conversation.error && !conversation.items.length)} />
      <div ref={layout.bottom} className="workspace-bottom">
        <Composer key={`composer:${sessions.selected ?? 'empty'}`} ready={conversation.ready} connected={conversation.connected}
          accessMode={approvals.snapshot?.mode ?? 'audit'} accessDisabled={!approvals.snapshot || approvals.pending || Boolean(approvals.snapshot.pending.length)}
          onAccessChange={approvals.setMode}
          approvals={<ApprovalPanel requests={approvals.snapshot?.pending ?? []} sessionId={sessions.selected}
            disabled={approvals.pending} onDecide={approvals.decide} onStop={approvals.stop} />}
          status={status} readOnly={readOnly}
          busy={conversation.busy} pending={conversation.pending} model={conversation.model} models={sessions.models}
          sessionId={sessions.selected} images={conversation.images} onUploaded={conversation.registerImage} onRenameImage={conversation.renameImage}
          acceptedGuidance={conversation.items.filter(item => item.kind === 'text' && item.guidance).map(item => item.id.slice('guidance:'.length))}
          onSend={conversation.send} onGuide={conversation.guide} onStop={conversation.stop} onModelChange={conversation.switchModel} />
      </div>
    </main>
  </div>;
}
