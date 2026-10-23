import { useEffect, useRef, useState } from 'react';
import type { Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';

export function ModelPicker({ groups, model, disabled, refreshing, error, onRefresh, onChange }: {
  groups: ModelGroup[]; model: Model | null; disabled: boolean;
  refreshing: boolean; error: string | null; onRefresh: () => Promise<void>;
  onChange: (provider: string, name: string) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const click = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) setOpen(false); };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', click); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', click); document.removeEventListener('keydown', key); };
  }, [open]);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  const visibleGroups = groups.filter(group => group.models.some(item => item.enabled));
  const display = groups.find(group => group.provider === model?.provider)?.models.find(item => item.id === model?.name)?.name ?? model?.name ?? '选择模型';

  return <div className="model-picker" ref={container}>
    <button type="button" ref={trigger} className="model-trigger" aria-expanded={open} aria-controls="model-options"
      disabled={disabled} onClick={() => setOpen(value => !value)} title={display}>
      <span>{display}</span><Icon name="down" size={14} />
    </button>
    <button type="button" className={`icon-button model-refresh ${refreshing ? 'refreshing' : ''}`}
      disabled={refreshing} aria-label={refreshing ? '正在刷新模型列表' : '刷新模型列表'}
      title={error ? `刷新失败：${error}；点击重试` : refreshing ? '正在刷新模型列表' : '刷新模型列表'}
      onClick={() => { if (!disabled) setOpen(true); void onRefresh(); }}>
      <Icon name="refresh" size={14} />
    </button>
    {open && <div id="model-options" className="model-options" role="group" aria-label="选择模型" aria-busy={refreshing}>
      {error && <div className="model-feedback model-error" role="alert">刷新模型列表失败：{error}。请点击刷新重试。</div>}
      {!visibleGroups.length && <div className="model-feedback" role="status">
        {refreshing ? '正在加载模型列表…' : '暂无可用模型，请刷新列表或检查提供商配置。'}
      </div>}
      {visibleGroups.map(group => <div key={group.provider}>
        <div className="model-group">{group.displayName}</div>
        {group.models.map(item => {
          const selected = model?.provider === group.provider && model.name === item.id;
          return <button type="button" key={item.id} className={`model-option ${selected ? 'selected' : ''}`}
            disabled={!item.enabled} aria-pressed={selected} onClick={async () => {
              if (await onChange(group.provider, item.id)) { setOpen(false); trigger.current?.focus(); }
            }}><span>{item.name}</span><span>{selected ? '✓' : !item.enabled ? '不可用' : ''}</span></button>;
        })}
      </div>)}
    </div>}
  </div>;
}
