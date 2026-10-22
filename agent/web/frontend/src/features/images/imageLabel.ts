import type { ImageAsset } from '../../api/types';

export function imageLabel(image: ImageAsset): string {
  return `${image.ordinal} / ${image.name}`;
}
