import { useEffect, useRef, useState } from 'react';
import type { Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ReasoningSlider } from './ReasoningSlider';
import { savedEffort, saveEffort } from './reasoningPreference';
import './modelPicker.css';

export function ModelPicker({ groups, model, disabled, refreshing, error, onRefresh, onChange }: {
  groups: ModelGroup[]; model: Model | null; disabled: boolean;
  refreshing: boolean; error: string | null; onRefresh: () => Promise<void>;
  onChange: (provider: string, name: string, effort?: string) => Promise<boolean>;
}) {
  const [page, setPage] = useState<'effort' | 'models' | null>(null);
  const [changing, setChanging] = useState(false);
  const open = page !== null;
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const visibleGroups = groups.filter(group => group.models.some(item => item.enabled));
  const hasModels = visibleGroups.length > 0;
  useEffect(() => {
    if (!page) return;
    const click = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) setPage(null); };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') {
      if (page === 'models' && model && hasModels) setPage('effort');
      else { setPage(null); trigger.current?.focus(); }
    } };
    document.addEventListener('pointerdown', click); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', click); document.removeEventListener('keydown', key); };
  }, [page, model, hasModels]);
  useEffect(() => { if (disabled && !changing) setPage(null); }, [disabled, changing]);
  const option = visibleGroups.find(group => group.provider === model?.provider)?.models.find(item => item.id === model?.name && item.enabled);
  const display = !visibleGroups.length ? refreshing ? '正在加载模型列表…' : '无可用模型'
    : option?.name ?? model?.name ?? '选择模型';
  const levels = option?.reasoning_efforts ?? [];
  const effort = [model?.reasoning_effort, option?.default_reasoning_effort, option?.api_default_reasoning_effort]
    .find(value => value && levels.includes(value)) ?? levels[0];
  useEffect(() => {
    if (page) panel.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"], .model-chip')?.focus();
  }, [page]);
  const heading = (label?: string) => <button type="button" className="model-chip" aria-label={`选择模型：${display}`}
    disabled={disabled || changing} onClick={() => setPage('models')}>
    {label && <strong>{label}</strong>}<span>{display} ›</span>
  </button>;
  async function select(provider: string, name: string, value?: string) {
    setChanging(true);
    try {
      if (!await onChange(provider, name, value)) return;
      if (value) saveEffort(provider, name, value);
      setPage(current => current === 'models' ? 'effort' : current);
    } finally { setChanging(false); }
  }

  return <div className="model-picker" ref={container}>
    <button type="button" ref={trigger} className="model-trigger" aria-expanded={open} aria-controls="model-options"
      disabled={disabled} onClick={() => setPage(open ? null : model && visibleGroups.length ? 'effort' : 'models')} title={display}>
      <span>{display}</span><Icon name="down" size={14} />
    </button>
    {!visibleGroups.length && <button type="button" className={`icon-button model-refresh ${refreshing ? 'refreshing' : ''}`}
      disabled={refreshing} aria-label={refreshing ? '正在刷新模型列表' : '刷新模型列表'}
      title={error ? `刷新失败：${error}；点击重试` : refreshing ? '正在刷新模型列表' : '刷新模型列表'}
      onClick={() => { if (!disabled) setPage('models'); void onRefresh(); }}>
      <Icon name="refresh" size={14} />
    </button>}
    {open && <div ref={panel} id="model-options" className={`model-options${page === 'effort' ? ' effort-panel' : ''}`} role="group" aria-label="选择模型" aria-busy={refreshing}>
      {error && <div className="model-feedback model-error" role="alert">刷新模型列表失败：{error}。{visibleGroups.length ? '请刷新网页重试。' : '请点击刷新重试。'}</div>}
      {!visibleGroups.length && <div className="model-feedback" role="status">
        {refreshing ? '正在加载模型列表…' : '无可用模型'}
      </div>}
      {page === 'effort' && model ? (levels.length > 1
        ? <ReasoningSlider key={JSON.stringify([model.provider, model.name])} levels={levels} value={effort} heading={heading}
          disabled={disabled || changing} onSelect={value => select(model.provider, model.name, value)} />
        : heading()) : visibleGroups.map(group => <div key={group.provider}>
        <div className="model-group">{group.displayName}</div>
        {group.models.map(item => {
          const selected = model?.provider === group.provider && model.name === item.id;
          return <button type="button" key={item.id} className={`model-option ${selected ? 'selected' : ''}`}
            disabled={!item.enabled || changing} aria-pressed={selected} onClick={() => {
              if (selected) setPage('effort');
              else void select(group.provider, item.id, savedEffort(group.provider, item));
            }}><span>{item.name}</span><span>{selected ? '✓' : !item.enabled ? '不可用' : ''}</span></button>;
        })}
      </div>)}
    </div>}
  </div>;
}
