import { useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { AccessMode, ImageAsset, Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ModelPicker } from '../models/ModelPicker';
import { useImageDraft } from '../images/useImageDraft';
import { ImageAttachments } from '../images/ImageAttachments';

interface Props {
  accessMode: AccessMode; accessDisabled: boolean; approvals: ReactNode;
  onAccessChange: (mode: AccessMode) => void;
  ready: boolean; connected: boolean; busy: boolean;
  status: string; readOnly: boolean;
  pending: 'send' | 'stop' | 'model' | 'image' | null;
  model: Model | null; models: ModelGroup[];
  sessionId: string | null; images: ImageAsset[];
  onUploaded: (image: ImageAsset) => void;
  onRenameImage: (id: string, name: string) => Promise<boolean>;
  onSend: (text: string, images: string[]) => Promise<boolean>;
  onStop: () => Promise<boolean>;
  onModelChange: (provider: string, model: string) => Promise<boolean>;
}

export function Composer(props: Props) {
  const [text, setText] = useState('');
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const draft = useImageDraft(props.sessionId, props.onUploaded);
  const textRef = useRef(text); textRef.current = text;
  useLayoutEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = 'auto'; element.style.height = `${Math.min(element.scrollHeight, 220)}px`; }
  }, [text]);
  const canEditImages = !props.readOnly && props.ready && props.connected && !props.busy && !props.pending && !draft.uploading;
  const disabled = (props.readOnly && !props.busy) || !props.ready || !props.connected || draft.uploading ||
    Boolean(props.pending && props.pending !== 'image') || (!props.busy && !text.trim() && !draft.ids.length);
  async function submit() {
    if (disabled) return;
    if (props.busy) { await props.onStop(); return; }
    const content = text;
    const images = [...draft.ids];
    if (await props.onSend(content, images)) {
      if (textRef.current === content) setText('');
      draft.remove(images);
      textarea.current?.focus();
    }
  }

  return <div className="composer-wrap">
    {props.approvals}
    <form className="composer" onSubmit={event => { event.preventDefault(); void submit(); }}
      onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
      onDrop={event => {
        event.preventDefault();
        if (canEditImages) void draft.upload(Array.from(event.dataTransfer.files));
      }}>
      {props.sessionId && <ImageAttachments sessionId={props.sessionId}
        images={draft.ids.map(id => props.images.find(image => image.id === id)).filter((image): image is ImageAsset => Boolean(image))}
        disabled={!canEditImages} onRename={props.onRenameImage} onRemove={id => draft.remove([id])} />}
      {draft.uploading && <div className="image-draft-status" role="status">正在上传图片…</div>}
      {draft.error && <div className="image-draft-status image-draft-error" role="alert">{draft.error}</div>}
      <textarea ref={textarea} rows={2} aria-label="消息" placeholder={props.readOnly ? '子 agent 会话仅供查看' : '输入消息…'} value={text}
        onPaste={event => {
          const files = Array.from(event.clipboardData.files).filter(file => file.type.startsWith('image/'));
          if (files.length && canEditImages) { event.preventDefault(); void draft.upload(files); }
        }}
        disabled={!props.ready || props.readOnly} onChange={event => setText(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
            event.preventDefault(); void submit();
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
        disabled={props.readOnly || !props.ready || !props.connected || props.busy || Boolean(props.pending)} onChange={props.onModelChange} />
        <button type="submit" className={`send-button ${props.busy ? 'stop-button' : ''}`} disabled={disabled}
          aria-label={props.busy ? '停止执行' : '发送消息'} title={props.busy ? '停止执行' : '发送消息'}>
          {props.busy ? <span className="stop-square" /> : <Icon name="arrow" size={20} />}
        </button>
        </div>
      </div>
    </form>
    <div className="composer-hint connection-status" role="status">
      <span className={`connection-dot ${props.connected ? 'connected' : ''}`} />
      {props.pending === 'stop' ? '正在停止…' : props.status}
    </div>
  </div>;
}
