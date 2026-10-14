import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { imageLabel, imageNumber } from './imageLabel';
import './images.css';

export interface ImageAttachmentProps {
  sessionId: string;
  images: ImageAsset[];
  disabled: boolean;
  onRename: (id: string, name: string) => Promise<boolean>;
  onRemove?: (id: string) => void;
}

function ImageCard({ image, ...props }: Omit<ImageAttachmentProps, 'images'> & { image: ImageAsset }) {
  const [name, setName] = useState(image.name);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setName(image.name); }, [image.name]);

  async function save() {
    if (saving || props.disabled || name === image.name) return;
    const value = name.trim();
    if (!value) { setName(image.name); return; }
    setSaving(true);
    try { setName(await props.onRename(image.id, value) ? value : image.name); }
    finally { setSaving(false); }
  }

  return <div className="image-card">
    <a href={api.imageUrl(props.sessionId, image.id)} target="_blank" rel="noopener noreferrer"
      aria-label={`查看图片：${imageLabel(image)}`}><img src={api.imageUrl(props.sessionId, image.id, true)}
        alt={imageLabel(image)} loading="lazy" width={160} height={110} /></a>
    {props.onRemove && <button type="button" className="image-remove icon-button" aria-label={`移除图片：${image.name}`}
      disabled={props.disabled || saving} onClick={() => props.onRemove?.(image.id)}><Icon name="close" size={14} /></button>}
    <label className="image-name"><span className="sr-only">图片名称</span>
      <span className="image-number">{imageNumber(image)} /</span>
      <input value={name} maxLength={80} disabled={props.disabled || saving} aria-label={`图片名称：${image.name}`}
        title="修改名称，按 Enter 或移开焦点保存" onChange={event => setName(event.target.value)}
        onBlur={() => { void save(); }} onKeyDown={event => {
          if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
            event.preventDefault(); event.stopPropagation(); event.currentTarget.blur();
          }
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setName(image.name); }
        }} />
    </label>
    <div className="image-info" title={`${image.filename} · ${image.width} × ${image.height}`}>
      {image.width} × {image.height} · {image.filename}
    </div>
  </div>;
}

export function ImageAttachments({ images, ...props }: ImageAttachmentProps) {
  if (!images.length) return null;
  return <div className="image-attachments">{images.map(image => <ImageCard key={image.id} image={image} {...props} />)}</div>;
}
