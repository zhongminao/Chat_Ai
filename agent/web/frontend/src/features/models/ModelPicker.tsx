import { useEffect, useRef, useState } from 'react';
import type { Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ReasoningSlider, effortLabel } from './ReasoningSlider';
import { savedEffort, saveEffort } from './reasoningPreference';
import './modelPicker.css';

const hasEffortOptions = (item?: ModelGroup['models'][number]) => (item?.reasoning_efforts?.length ?? 0) > 1;

export function ModelPicker({ groups, model, disabled, refreshing, error, onRefresh, onChange }: {
  groups: ModelGroup[]; model: Model | null; disabled: boolean;
  refreshing: boolean; error: string | null; onRefresh: () => Promise<void>;
  onChange: (provider: string, name: string, effort?: string) => Promise<boolean>;
}) {
  const [requestedPage, setPage] = useState<'effort' | 'models' | null>(null);
  const [changing, setChanging] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const visibleGroups = groups.filter(group => group.models.some(item => item.enabled));
  const hasModels = visibleGroups.length > 0;
  const option = visibleGroups.find(group => group.provider === model?.provider)?.models.find(item => item.id === model?.name && item.enabled);
  const display = !hasModels ? refreshing ? '正在加载模型列表…' : '无可用模型'
    : option?.name ?? model?.name ?? '选择模型';
  const levels = option?.reasoning_efforts ?? [];
  const currentEffort = model?.provider === 'deepseek' && model.thinking === 'disabled' ? 'none' : model?.reasoning_effort;
  const effort = [currentEffort, option?.default_reasoning_effort]
    .find(value => value && levels.includes(value)) ?? levels[0];
  const hasEffort = hasEffortOptions(option);
  const page = requestedPage === 'effort' && !hasEffort ? 'models' : requestedPage;
  const open = page !== null;
  useEffect(() => {
    if (!page) return;
    const click = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) setPage(null); };
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') {
      if (page === 'models' && hasEffort && !changing) setPage('effort');
      else { setPage(null); trigger.current?.focus(); }
    } };
    document.addEventListener('pointerdown', click); document.addEventListener('keydown', key);
    return () => { document.removeEventListener('pointerdown', click); document.removeEventListener('keydown', key); };
  }, [page, hasEffort, changing]);
  useEffect(() => { if (disabled) setPage(null); }, [disabled]);
  useEffect(() => {
    if (page && !changing) panel.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"], .model-chip')?.focus();
  }, [page, changing]);
  const heading = (label?: string) => <button type="button" className="model-chip" aria-label={`选择模型：${display}`}
    disabled={disabled || changing} onClick={() => setPage('models')}>
    {label && <strong>{label}</strong>}<span>{display} ›</span>
  </button>;
  async function select(provider: string, name: string, value?: string, nextPage?: 'effort' | null) {
    setChanging(true);
    try {
      if (!await onChange(provider, name, value)) return;
      if (value) saveEffort(provider, name, value);
      if (nextPage !== undefined) setPage(current => current === 'models' ? nextPage : current);
    } finally { setChanging(false); }
  }

  return <div className="model-picker" ref={container}>
    <button type="button" ref={trigger} className="model-trigger" aria-expanded={open} aria-controls="model-options"
      disabled={disabled || changing} onClick={() => setPage(open ? null : hasEffort ? 'effort' : 'models')} title={display}>
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
      {page === 'effort' && model ? <ReasoningSlider key={JSON.stringify([model.provider, model.name])} levels={levels} value={effort} heading={heading}
          disabled={disabled || changing} onSelect={value => select(model.provider, model.name, value)} /> : visibleGroups.map(group => <div key={group.provider}>
        <div className="model-group">{group.displayName}</div>
        {group.models.map(item => {
          const selected = model?.provider === group.provider && model.name === item.id;
          const preferred = !selected && item.enabled && hasEffortOptions(item) ? savedEffort(group.provider, item) : undefined;
          const level = selected ? effort : preferred ?? item.default_reasoning_effort;
          const showLevel = item.enabled && hasEffortOptions(item) && level && item.reasoning_efforts?.includes(level);
          return <button type="button" key={item.id} className={`model-option ${selected ? 'selected' : ''}`}
            disabled={disabled || !item.enabled || changing} aria-pressed={selected} onClick={() => {
              const next = hasEffortOptions(item) ? 'effort' : null;
              if (selected) { setPage(next); if (!next) trigger.current?.focus(); }
              else void select(group.provider, item.id, preferred, next);
            }}><span>{item.name}</span><span>{!item.enabled ? '不可用' : <>{showLevel && effortLabel(level)}{selected && (showLevel ? ' ✓' : '✓')}</>}</span></button>;
        })}
      </div>)}
    </div>}
  </div>;
}
