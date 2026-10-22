import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { imageLabel } from './imageLabel';
import './images.css';

export interface ImageAttachmentProps {
  sessionId: string;
  images: ImageAsset[];
  disabled?: boolean;
  onRemove?: (id: string) => void;
}

function ImageCard({ image, ...props }: Omit<ImageAttachmentProps, 'images'> & { image: ImageAsset }) {
  return <div className="image-card">
    <a href={api.imageUrl(props.sessionId, image.id)} target="_blank" rel="noopener noreferrer"
      aria-label={`查看图片：${imageLabel(image)}`}><img src={api.imageUrl(props.sessionId, image.id, true)}
        alt={imageLabel(image)} loading="lazy" width={160} height={110} /></a>
    {props.onRemove && <button type="button" className="image-remove icon-button" aria-label={`移除图片：${image.name}`}
      disabled={props.disabled} onClick={() => props.onRemove?.(image.id)}><Icon name="close" size={14} /></button>}
    <div className="image-name" title={imageLabel(image)}>{imageLabel(image)}</div>
  </div>;
}

export function ImageAttachments({ images, ...props }: ImageAttachmentProps) {
  if (!images.length) return null;
  return <div className="image-attachments">{images.map(image => <ImageCard key={image.id} image={image} {...props} />)}</div>;
}
