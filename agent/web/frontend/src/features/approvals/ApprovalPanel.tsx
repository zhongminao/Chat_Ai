import type { ApprovalRequest } from '../../api/types';

export function ApprovalPanel({ requests, sessionId, disabled, onDecide, onStop }: {
  requests: ApprovalRequest[]; sessionId: string | null; disabled: boolean;
  onDecide: (id: string, approved: boolean) => void;
  onStop: (session: string) => void;
}) {
  if (!requests.length) return null;
  return <section className="approval-panel" aria-label="待审批操作" aria-live="polite">
    {requests.map(item => <article className="approval-card" key={item.id}>
      <div className="approval-heading"><strong>等待批准本次操作</strong>
        <span>{item.sessionId === sessionId ? '当前 Agent' : `其他 Agent · ${item.sessionId.slice(0, 8)}`}</span></div>
      <div className="approval-tool">{item.tool}</div>
      {item.workspace && <div className="approval-field">工作目录：{item.workspace}</div>}
      <details open><summary>查看完整操作内容</summary>
        {Object.entries(item.arguments).map(([name, value]) => <div key={name}>
          <div className="approval-field">{name}</div>
          <pre>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
        </div>)}
      </details>
      <div className="approval-actions">
        <button className="approval-approve" disabled={disabled} onClick={() => onDecide(item.id, true)}>批准本次</button>
        <button disabled={disabled} onClick={() => onDecide(item.id, false)}>拒绝本次</button>
        <button disabled={disabled} onClick={() => onStop(item.sessionId)}>停止此任务</button>
      </div>
    </article>)}
  </section>;
}
