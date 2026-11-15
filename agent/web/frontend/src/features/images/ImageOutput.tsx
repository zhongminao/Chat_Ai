import { useState } from 'react';
import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { imageLabel } from './imageLabel';
import './imageOutput.css';

function OutputImage({ image, sessionId, thumbnail }: { image: ImageAsset; sessionId: string; thumbnail: boolean }) {
  const [failed, setFailed] = useState(false);
  const url = api.imageUrl(sessionId, image.id);
  const label = imageLabel(image);
  return <figure className="image-output">
    {failed ? <div className="image-output-error" role="alert">图片加载失败，可尝试查看原图</div>
      : <a className="image-output-preview" href={url} target="_blank" rel="noopener noreferrer" aria-label={`查看原图：${label}`}>
        <img src={thumbnail ? api.imageUrl(sessionId, image.id, true) : url} alt={label} width={image.width} height={image.height} loading="lazy" decoding="async"
          onError={() => setFailed(true)} />
      </a>}
    <figcaption><span className="image-output-name" title={`${label} · ${image.filename}`}>{label}</span>
      <span className="image-output-actions"><a href={url} target="_blank" rel="noopener noreferrer">查看原图</a>
        <a href={url} download={image.filename}>下载</a></span>
    </figcaption>
  </figure>;
}

export function ImageOutput({ ids, assets, sessionId, thumbnail = false }: {
  ids: string[]; assets: ImageAsset[]; sessionId: string; thumbnail?: boolean;
}) {
  const images = ids.map(id => assets.find(image => image.id === id)).filter((image): image is ImageAsset => Boolean(image));
  if (!images.length) return null;
  return <div className={`image-outputs${thumbnail ? " image-outputs-thumbnails" : ""}`}>{images.map(image =>
    <OutputImage key={image.id} image={image} sessionId={sessionId} thumbnail={thumbnail} />)}</div>;
}
