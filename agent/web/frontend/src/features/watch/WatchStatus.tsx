import { useWatch } from './useWatch';

export function WatchStatus({ sessionId, onChange }: {
  sessionId: string | null; onChange: () => void;
}) {
  const watch = useWatch(sessionId, onChange);
  if (!sessionId || (!watch.resources.length && !watch.error)) return null;
  const agents = watch.resources.filter(item => item.kind === 'agent');
  const running = agents.filter(item => item.status === 'running').length;
  const finished = agents.length - running;
  return <div className="watch-panel" aria-label="后台任务状态">
    {watch.error ? <><span>后台状态连接中断</span><button onClick={watch.retry}>重试</button></>
      : <span>后台任务：<span className="watch-counts">{running} 个运行中 · {finished} 个已结束</span></span>}
  </div>;
}
