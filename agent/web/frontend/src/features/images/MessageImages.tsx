import type { ImageAsset } from '../../api/types';
import { ImageAttachments } from './ImageAttachments';

export function MessageImages({ ids, assets, ...props }: {
  ids: string[]; assets: ImageAsset[]; sessionId: string;
}) {
  const images = ids.map(id => assets.find(image => image.id === id)).filter((image): image is ImageAsset => Boolean(image));
  return <ImageAttachments images={images} {...props} />;
}
