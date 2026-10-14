import { useLayoutEffect, useRef, useState } from 'react';
import type { ImageAsset, Model, ModelGroup } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { ModelPicker } from '../models/ModelPicker';
import { useImageDraft } from '../images/useImageDraft';
import { ImageAttachments } from '../images/ImageAttachments';

interface Props {
  ready: boolean; connected: boolean; busy: boolean;
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
  const canEditImages = props.ready && props.connected && !props.busy && !props.pending && !draft.uploading;
  const disabled = !props.ready || !props.connected || draft.uploading ||
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
      <textarea ref={textarea} rows={2} aria-label="消息" placeholder="输入消息…" value={text}
        onPaste={event => {
          const files = Array.from(event.clipboardData.files).filter(file => file.type.startsWith('image/'));
          if (files.length && canEditImages) { event.preventDefault(); void draft.upload(files); }
        }}
        disabled={!props.ready} onChange={event => setText(event.target.value)} onKeyDown={event => {
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
        <ModelPicker groups={props.models} model={props.model}
        disabled={!props.ready || !props.connected || props.busy || Boolean(props.pending)} onChange={props.onModelChange} />
        </div>
        <button type="submit" className={`send-button ${props.busy ? 'stop-button' : ''}`} disabled={disabled}
          aria-label={props.busy ? '停止执行' : '发送消息'} title={props.busy ? '停止执行' : '发送消息'}>
          {props.busy ? <span className="stop-square" /> : <Icon name="arrow" size={20} />}
        </button>
      </div>
    </form>
    <div className="composer-hint">{props.pending === 'stop' ? '正在请求停止…' : 'Enter 发送 · Shift + Enter 换行'}</div>
  </div>;
}
