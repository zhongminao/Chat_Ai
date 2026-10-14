import type { ImageAsset } from '../../api/types';

export function imageNumber(image: ImageAsset): string {
  return String(image.ordinal).padStart(2, '0');
}

export function imageLabel(image: ImageAsset): string {
  return `${imageNumber(image)} / ${image.name}`;
}
