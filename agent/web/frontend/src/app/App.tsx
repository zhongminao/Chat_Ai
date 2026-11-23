import { useState } from 'react';
import { useTabTitle } from './useTabTitle';
import { useSessionReadState } from '../features/sessions/useSessionReadState';
import { useSessions } from '../features/sessions/useSessions';
import { SessionSidebar } from '../features/sessions/SessionSidebar';
import { useNewConversation } from '../features/conversation/useNewConversation';
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
  const approvals = useApprovals(sessions.selected);
  const conversation = useConversation(sessions.selected, () => { void sessions.refresh(); });
  const newConversation = useNewConversation(id => { sessions.select(id); void sessions.refresh(); }, sessions.defaultModel, sessions.models);
  const isDraft = sessions.selected === null;
  const draftSending = isDraft && newConversation.sending;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const openSidebar = () => { setSidebarOpen(true); setSidebarCollapsed(false); };
  const closeSidebar = () => { setSidebarOpen(false); setSidebarCollapsed(true); };
  const current = sessions.sessions.find(item => item.id === sessions.selected);
  const readThrough = useSessionReadState(sessions.sessions, sessions.selected, conversation.ready, conversation.seq);
  const mainId = current?.parent_session_id ?? sessions.selected;
  const hasChildAgents = Boolean(mainId && sessions.sessions.some(item => item.parent_session_id === mainId));
  const readOnly = Boolean(current?.parent_session_id || conversation.session?.parent_session_id);
  const error = sessions.error || (isDraft ? newConversation.error : conversation.error || approvals.error);
  const waitingCallIds = (approvals.snapshot?.pending ?? []).filter(item => item.sessionId === sessions.selected).map(item => item.callId);
  const waitingQuestion = conversation.items.some(item => item.kind === 'question' && item.status === 'pending');
  useTabTitle({
    selected: sessions.selected, title: current?.title, loading: sessions.loading,
    connected: conversation.connected, ready: conversation.ready, busy: conversation.busy,
    sending: isDraft ? draftSending : conversation.pending === 'send', waitingApproval: waitingCallIds.length > 0, waitingQuestion,
    error, history: conversation.history, live: conversation.live,
  });

  return <div className={`app-layout${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
    <SessionSidebar sessions={sessions.sessions} selected={sessions.selected} loading={sessions.loading}
      deleting={sessions.deleting} busy={conversation.busy} open={sidebarOpen}
      updating={sessions.updating} onUpdate={sessions.update} readThrough={readThrough}
      activeBusy={conversation.ready ? conversation.busy : undefined}
      onClose={closeSidebar} onSelect={id => { sessions.select(id); setSidebarOpen(false); }}
      onCreate={() => { sessions.select(null); setSidebarOpen(false); }} onDelete={id => { void sessions.remove(id); }} />
    <main className={`workspace${hasChildAgents ? "" : " no-agent-header"}`}>
      <div className="workspace-top">
        {hasChildAgents ? <header className="workspace-header">
          <button className="icon-button sidebar-open" aria-label="打开会话列表" aria-controls="session-sidebar" onClick={openSidebar}><Icon name="menu" /></button>
          <AgentTabs sessions={sessions.sessions} selected={sessions.selected} onSelect={sessions.select}>
            <WatchStatus sessionId={mainId} onChange={() => { void sessions.refresh(); }} />
          </AgentTabs>
        </header> : <>
          <div hidden><WatchStatus sessionId={mainId} onChange={() => { void sessions.refresh(); }} /></div>
          <button className="icon-button sidebar-open sidebar-open-no-header" aria-label="打开会话列表" aria-controls="session-sidebar"
            onClick={openSidebar}><Icon name="menu" /></button>
        </>}
        {error && <div className="error-banner" role="alert"><span>{error}</span>
          {!isDraft && conversation.error && !conversation.ready && <button onClick={conversation.retryHistory}>重新打开会话</button>}
          {sessions.error && <button onClick={sessions.retry}>重试</button>}
          {sessions.error && sessions.selected && <button className="icon-button" aria-label="关闭错误提示" onClick={sessions.clearError}><Icon name="close" size={16} /></button>}
        </div>}
      </div>
      <MessageList key={`messages:${sessions.selected ?? 'empty'}`} items={conversation.items} busy={conversation.busy} assistantId={conversation.assistantId}
        waitingCallIds={waitingCallIds} hasMore={conversation.hasMore} loadingMore={conversation.loadingMore}
        historyError={conversation.historyError} onLoadMore={() => { void conversation.loadMore(); }} revision={conversation.revision}
        sessionId={sessions.selected} images={conversation.images} canAnswer={conversation.ready && conversation.connected}
        loading={sessions.loading || Boolean(sessions.selected && !conversation.ready && !conversation.error && !conversation.items.length)}
        footer={
          <Composer key={`composer:${sessions.selected ?? 'empty'}`} ready={isDraft ? !sessions.loading : conversation.ready} connected={isDraft || conversation.connected}
            accessMode={isDraft ? newConversation.accessMode : approvals.snapshot?.mode ?? 'audit'}
            accessDisabled={isDraft ? draftSending : !approvals.snapshot || approvals.pending || Boolean(approvals.snapshot.pending.length)}
            onAccessChange={isDraft ? newConversation.setAccessMode : approvals.setMode}
            approvals={<ApprovalPanel requests={approvals.snapshot?.pending ?? []} sessionId={sessions.selected}
              disabled={approvals.pending} onDecide={approvals.decide} onStop={approvals.stop} />}
            contextUsage={conversation.contextUsage} readOnly={readOnly}
            busy={!isDraft && conversation.busy} pending={isDraft ? draftSending ? 'send' : null : conversation.pending} model={isDraft ? newConversation.model : conversation.model} models={sessions.models}
            modelsRefreshing={sessions.modelsRefreshing} modelsError={sessions.modelsError} onRefreshModels={sessions.refreshModels}
            sessionId={sessions.selected} images={conversation.images} onUploaded={conversation.registerImage}
            acceptedGuidance={conversation.items.filter(item => item.kind === 'text' && item.guidance).map(item => item.id.slice('guidance:'.length))}
            onSend={isDraft ? newConversation.send : conversation.send} onGuide={conversation.guide} onStop={conversation.stop} onModelChange={isDraft ? newConversation.selectModel : conversation.switchModel} />
        } />
    </main>
  </div>;
}
