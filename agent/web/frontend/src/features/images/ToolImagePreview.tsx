import { useState } from 'react';
import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { imageLabel } from './imageLabel';
import './toolImagePreview.css';

function PreviewImage({ image, sessionId }: { image: ImageAsset; sessionId: string }) {
  const [failed, setFailed] = useState(false);
  const url = api.imageUrl(sessionId, image.id);
  const label = imageLabel(image);
  return <figure className="tool-image-preview">
    {failed ? <div className="tool-image-preview-error" role="alert">图片加载失败，可尝试查看原图</div>
      : <a className="tool-image-preview-link" href={url} target="_blank" rel="noopener noreferrer" aria-label={`查看原图：${label}`}>
        <img src={api.imageUrl(sessionId, image.id, true)} alt={label} width={image.width} height={image.height} loading="lazy" decoding="async"
          onError={() => setFailed(true)} />
      </a>}
    <figcaption><span className="tool-image-preview-name" title={`${label} · ${image.filename}`}>{label}</span>
      <span className="tool-image-preview-actions"><a href={url} target="_blank" rel="noopener noreferrer">查看原图</a>
        <a href={url} download={image.filename}>下载</a></span>
    </figcaption>
  </figure>;
}

export function ToolImagePreview({ ids, assets, sessionId }: {
  ids: string[]; assets: ImageAsset[]; sessionId: string;
}) {
  const images = ids.map(id => assets.find(image => image.id === id)).filter((image): image is ImageAsset => Boolean(image));
  if (!images.length) return null;
  return <div className="tool-image-previews">{images.map(image =>
    <PreviewImage key={image.id} image={image} sessionId={sessionId} />)}</div>;
}
