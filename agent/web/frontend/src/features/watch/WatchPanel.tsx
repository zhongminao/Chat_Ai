import { useWatch } from './useWatch';

export function WatchPanel({ sessionId, disabled, onSend, onChange }: {
  sessionId: string | null; disabled: boolean;
  onSend: (text: string) => Promise<boolean>; onChange: () => void;
}) {
  const watch = useWatch(sessionId, onChange);
  if (!sessionId || (!watch.resources.length && !watch.error)) return null;
  const running = watch.resources.filter(item => item.status === 'running').length;
  const finished = watch.resources.filter(item => item.status !== 'running');
  return <div className="watch-panel" aria-label="后台任务状态">
    <span>{watch.error ? '后台状态连接中断' : `后台任务：${running} 个运行中 · ${finished.length} 个已结束`}</span>
    {watch.error ? <button onClick={watch.retry}>重试</button>
      : finished.length > 0 && <button disabled={disabled} onClick={() => {
        void onSend(`请调用 watch 查看并处理这些后台任务的结果：${finished.map(item => item.id).join('、')}。按需读取 result_path 中的报告。`);
      }}>交给主 agent</button>}
  </div>;
}
