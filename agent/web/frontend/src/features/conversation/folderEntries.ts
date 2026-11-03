/** Browser folder selection and dropped-directory traversal. */
export interface FolderEntry { file: File; path: string }
export interface SelectedFolder { name: string; entries: FolderEntry[] }

export function selectedFolder(files: File[]): SelectedFolder | null {
  if (!files.length) return null;
  const name = files[0].webkitRelativePath.split('/')[0];
  const entries = files.map(file => ({ file, path: file.webkitRelativePath.slice(name.length + 1) }));
  if (!name || entries.some(({ file, path }) => !path || !file.webkitRelativePath.startsWith(`${name}/`))) return null;
  return { name, entries };
}

async function contents(entry: FileSystemDirectoryEntry, prefix = ''): Promise<FolderEntry[]> {
  const reader = entry.createReader();
  const result: FolderEntry[] = [];
  for (;;) {
    // Chromium returns directory entries in batches, often capped at 100.
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) return result;
    for (const child of batch) {
      const path = `${prefix}${child.name}`;
      if (child.isDirectory) result.push(...await contents(child as FileSystemDirectoryEntry, `${path}/`));
      else if (child.isFile) {
        const file = await new Promise<File>((resolve, reject) => (child as FileSystemFileEntry).file(resolve, reject));
        result.push({ file, path });
      }
    }
  }
}

export async function droppedAttachments(items: DataTransferItemList): Promise<{ files: File[]; folders: SelectedFolder[] }> {
  // Drag data is only available during the drop event: capture handles before awaiting.
  const captured = Array.from(items).filter(item => item.kind === 'file').map(item => {
    const entry = item.webkitGetAsEntry?.();
    return { entry, file: entry?.isDirectory ? null : item.getAsFile() };
  });
  const files: File[] = [];
  const folders: SelectedFolder[] = [];
  for (const { entry, file } of captured) {
    if (entry?.isDirectory) {
      const entries = await contents(entry as FileSystemDirectoryEntry);
      if (entries.length) folders.push({ name: entry.name, entries });
    } else if (file) files.push(file);
  }
  return { files, folders };
}
