import { useEffect, useRef, useState } from 'react';
import type { Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';

export function ModelPicker({ groups, model, disabled, onChange }: {
  groups: ModelGroup[]; model: Model | null; disabled: boolean;
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
  const display = groups.find(group => group.provider === model?.provider)?.models.find(item => item.id === model?.name)?.name ?? model?.name ?? '选择模型';

  return <div className="model-picker" ref={container}>
    <button type="button" ref={trigger} className="model-trigger" aria-expanded={open} aria-controls="model-options"
      disabled={disabled} onClick={() => setOpen(value => !value)} title={display}>
      <span>{display}</span><Icon name="down" size={14} />
    </button>
    {open && <div id="model-options" className="model-options" role="group" aria-label="选择模型">
      {groups.map(group => <div key={group.provider}>
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
