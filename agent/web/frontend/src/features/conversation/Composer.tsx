import { useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { AccessMode, ContextUsage, ImageAsset, Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ModelPicker } from '../models/ModelPicker';
import { useImageDraft } from '../images/useImageDraft';
import { ImageAttachments } from '../images/ImageAttachments';
import { ContextMeter } from './ContextMeter';
import { GuidanceQueue } from './GuidanceQueue';
import { useGuidanceQueue } from './useGuidanceQueue';

interface Props {
  contextUsage?: ContextUsage | null;
  accessMode: AccessMode; accessDisabled: boolean; approvals: ReactNode;
  onAccessChange: (mode: AccessMode) => void;
  ready: boolean; connected: boolean; busy: boolean;
  status: string; readOnly: boolean;
  pending: 'send' | 'guide' | 'stop' | 'model' | null;
  model: Model | null; models: ModelGroup[];
  modelsRefreshing: boolean; modelsError: string | null; onRefreshModels: () => Promise<void>;
  sessionId: string | null; images: ImageAsset[];
  onUploaded: (image: ImageAsset) => void;
  onSend: (text: string, images: string[]) => Promise<boolean>;
  onGuide: (id: string, text: string, images: string[]) => Promise<boolean>;
  acceptedGuidance: string[];
  onStop: () => Promise<boolean>;
  onModelChange: (provider: string, model: string) => Promise<boolean>;
}

export function Composer(props: Props) {
  const [text, setText] = useState('');
  const [editingGuidance, setEditingGuidance] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const draft = useImageDraft(props.sessionId, props.onUploaded);
  const guidance = useGuidanceQueue(props.sessionId, props.acceptedGuidance);
  const queueInput = props.busy || editingGuidance || guidance.items.length > 0;
  const textRef = useRef(text); textRef.current = text;
  useLayoutEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = 'auto'; element.style.height = `${Math.min(element.scrollHeight, 220)}px`; }
  }, [text]);
  const canEditImages = !props.readOnly && props.ready && props.connected && !props.pending && !draft.uploading;
  const hasInput = Boolean(text.trim() || draft.ids.length);
  const stopAction = props.busy && !hasInput;
  const disabled = (props.readOnly && !stopAction) || !props.ready || !props.connected ||
    Boolean(props.pending) || (!stopAction && (draft.uploading || !hasInput));
  async function submit() {
    if (disabled) return;
    if (stopAction) { await props.onStop(); return; }
    const content = text;
    const images = [...draft.ids];
    if (queueInput) {
      guidance.add(content, images);
      setText(''); setEditingGuidance(false); draft.remove(images);
    } else if (await props.onSend(content, images)) {
      if (textRef.current === content) setText('');
      draft.remove(images);
      textarea.current?.focus();
    }
  }

  return <div className="composer-wrap">
    {props.approvals}
    <GuidanceQueue items={guidance.items} disabled={props.readOnly || !props.ready || !props.connected || Boolean(props.pending)}
      canEdit={!text.trim() && !draft.ids.length && !draft.uploading} onRemove={guidance.remove}
      onEdit={item => { guidance.remove(item.id); setText(item.text); setEditingGuidance(true); draft.restore(item.images); textarea.current?.focus(); }}
      onGuide={item => { void props.onGuide(item.id, item.text, item.images).then(sent => { if (sent) guidance.remove(item.id); }); }} />
    <form className="composer" onSubmit={event => { event.preventDefault(); void submit(); }}
      onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
      onDrop={event => {
        event.preventDefault();
        if (canEditImages) void draft.upload(Array.from(event.dataTransfer.files));
      }}>
      {props.sessionId && <ImageAttachments sessionId={props.sessionId}
        images={draft.ids.map(id => props.images.find(image => image.id === id)).filter((image): image is ImageAsset => Boolean(image))}
        disabled={!canEditImages} onRemove={id => draft.remove([id])} />}
      {draft.uploading && <div className="image-draft-status" role="status">正在上传图片…</div>}
      {draft.error && <div className="image-draft-status image-draft-error" role="alert">{draft.error}</div>}
      <textarea ref={textarea} rows={2} aria-label="消息" placeholder={props.readOnly ? '子 agent 会话仅供查看' : '输入消息…'} value={text}
        onPaste={event => {
          const files = Array.from(event.clipboardData.files).filter(file => file.type.startsWith('image/'));
          if (files.length && canEditImages) { event.preventDefault(); void draft.upload(files); }
        }}
        disabled={!props.ready || props.readOnly} onChange={event => setText(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault(); if (hasInput) void submit();
          }
        }} />
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden
        disabled={!canEditImages} onChange={event => {
          void draft.upload(Array.from(event.target.files ?? [])); event.target.value = '';
        }} />
      <div className="composer-actions"><div className="composer-left-actions">
        <button type="button" className="icon-button image-upload-button" aria-label="添加图片" title="选择图片，也可粘贴或拖入图片"
          disabled={!canEditImages || draft.ids.length >= 8} onClick={() => fileInput.current?.click()}><Icon name="image" /></button>
        <select className={`access-picker ${props.accessMode}`} aria-label="访问模式" value={props.accessMode}
          disabled={props.accessDisabled} onChange={event => props.onAccessChange(event.target.value as AccessMode)}>
          <option value="audit">审计</option><option value="full_access">完全访问</option>
        </select>
        </div><div className="composer-right-actions">
        <ModelPicker groups={props.models} model={props.model}
        refreshing={props.modelsRefreshing} error={props.modelsError} onRefresh={props.onRefreshModels}
        disabled={props.readOnly || !props.ready || !props.connected || props.busy || Boolean(props.pending)} onChange={props.onModelChange} />
        <button type="submit" className={`send-button ${stopAction ? 'stop-button' : ''}`} disabled={disabled}
          aria-label={stopAction ? '停止执行' : queueInput ? '加入引导队列' : '发送消息'}
          title={stopAction ? '停止执行' : queueInput ? '加入前端队列，点击引导后才发送' : '发送消息'}>
          {stopAction ? <span className="stop-square" /> : <Icon name="arrow" size={20} />}
        </button>
        </div>
      </div>
    </form>
    <div className="composer-hint connection-status" role="status">
      <ContextMeter usage={props.contextUsage} />
      <span className={`connection-dot ${props.connected ? 'connected' : ''}`} />
      {props.pending === 'stop' ? '正在停止…' : props.status}
    </div>
  </div>;
}
