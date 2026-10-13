import { useLayoutEffect, useRef, useState } from 'react';
import type { Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ModelPicker } from '../models/ModelPicker';

interface Props {
  ready: boolean; connected: boolean; busy: boolean;
  pending: 'send' | 'stop' | 'model' | null;
  model: Model | null; models: ModelGroup[];
  onSend: (text: string) => Promise<boolean>;
  onStop: () => Promise<boolean>;
  onModelChange: (provider: string, model: string) => Promise<boolean>;
}

export function Composer(props: Props) {
  const [text, setText] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);
  const textRef = useRef(text); textRef.current = text;
  useLayoutEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = 'auto'; element.style.height = `${Math.min(element.scrollHeight, 220)}px`; }
  }, [text]);
  const disabled = !props.ready || !props.connected || Boolean(props.pending) || (!props.busy && !text.trim());
  async function submit() {
    if (disabled) return;
    if (props.busy) { await props.onStop(); return; }
    const content = text;
    if (await props.onSend(content)) {
      if (textRef.current === content) setText('');
      textarea.current?.focus();
    }
  }

  return <div className="composer-wrap">
    <form className="composer" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <textarea ref={textarea} rows={2} aria-label="消息" placeholder="输入消息…" value={text}
        disabled={!props.ready} onChange={event => setText(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault(); void submit();
          }
        }} />
      <div className="composer-actions"><ModelPicker groups={props.models} model={props.model}
        disabled={!props.ready || !props.connected || props.busy || Boolean(props.pending)} onChange={props.onModelChange} />
        <button type="submit" className={`send-button ${props.busy ? 'stop-button' : ''}`} disabled={disabled}
          aria-label={props.busy ? '停止执行' : '发送消息'} title={props.busy ? '停止执行' : '发送消息'}>
          {props.busy ? <span className="stop-square" /> : <Icon name="arrow" size={20} />}
        </button>
      </div>
    </form>
    <div className="composer-hint">{props.pending === 'stop' ? '正在请求停止…' : 'Enter 发送 · Shift + Enter 换行'}</div>
  </div>;
}
