import { useState } from 'react';
import { useSessions } from '../features/sessions/useSessions';
import { SessionSidebar } from '../features/sessions/SessionSidebar';
import { useConversation } from '../features/conversation/useConversation';
import { MessageList } from '../features/conversation/MessageList';
import { Composer } from '../features/conversation/Composer';
import { Icon } from '../ui/Icon';
import { WatchPanel } from '../features/watch/WatchPanel';
import { AgentTabs } from '../features/sessions/AgentTabs';

export function App() {
  const sessions = useSessions();
  const conversation = useConversation(sessions.selected, () => { void sessions.refresh(); });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const current = sessions.sessions.find(item => item.id === sessions.selected);
  const readOnly = Boolean(current?.parent_session_id || conversation.snapshot?.parent_session_id);
  const error = sessions.error || conversation.error;
  const status = sessions.loading ? '正在加载' : !sessions.selected ? '未选择会话'
    : !conversation.connected ? '正在连接' : !conversation.ready ? '正在恢复会话'
    : conversation.busy ? '正在执行' : '已连接';

  return <div className="app-layout">
    <SessionSidebar sessions={sessions.sessions} selected={sessions.selected} loading={sessions.loading}
      creating={sessions.creating} deleting={sessions.deleting} busy={conversation.busy} open={sidebarOpen}
      renaming={sessions.renaming} onRename={sessions.rename}
      onClose={() => setSidebarOpen(false)} onSelect={id => { sessions.select(id); setSidebarOpen(false); }}
      onCreate={() => { void sessions.create(); setSidebarOpen(false); }} onDelete={id => { void sessions.remove(id); }} />
    <main className="workspace">
      <header className="workspace-header">
        <button className="icon-button mobile-only" aria-label="打开会话列表" onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button>
        <AgentTabs sessions={sessions.sessions} selected={sessions.selected} onSelect={sessions.select}>
          <WatchPanel sessionId={current?.parent_session_id ?? sessions.selected}
            onChange={() => { void sessions.refresh(); }} />
        </AgentTabs>
      </header>
      {error && <div className="error-banner" role="alert"><span>{error}</span>
        {!sessions.selected && <button onClick={sessions.retry}>重试</button>}
        {sessions.error && sessions.selected && <button className="icon-button" aria-label="关闭错误提示" onClick={sessions.clearError}><Icon name="close" size={16} /></button>}
      </div>}
      <MessageList key={`messages:${sessions.selected ?? 'empty'}`} items={conversation.items} busy={conversation.busy} assistantId={conversation.assistantId}
        sessionId={sessions.selected} images={conversation.images} editingImage={Boolean(conversation.pending)} onRenameImage={conversation.renameImage}
        loading={sessions.loading || Boolean(sessions.selected && !conversation.ready && !conversation.error)} />
      <Composer key={`composer:${sessions.selected ?? 'empty'}`} ready={conversation.ready} connected={conversation.connected}
        status={status} readOnly={readOnly}
        busy={conversation.busy} pending={conversation.pending} model={conversation.model} models={sessions.models}
        sessionId={sessions.selected} images={conversation.images} onUploaded={conversation.registerImage} onRenameImage={conversation.renameImage}
        onSend={conversation.send} onStop={conversation.stop} onModelChange={conversation.switchModel} />
    </main>
  </div>;
}
