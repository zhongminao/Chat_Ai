/** Browser folder selection and dropped-directory traversal. */
export interface FolderEntry { file: File; path: string }
export interface SelectedFolder { name: string; entries: FolderEntry[] }

export function selectedFolder(files: File[]): SelectedFolder {
  if (!files.length) throw new Error('未读取到文件夹中的文件（0 个文件）。请确认文件夹非空，或尝试拖拽文件夹上传。');
  const firstPath = files[0].webkitRelativePath;
  const name = firstPath?.split('/')[0];
  if (!name || files.some(file => !file.webkitRelativePath?.startsWith(`${name}/`) ||
      !file.webkitRelativePath.slice(name.length + 1))) {
    const sample = firstPath ? JSON.stringify(firstPath.slice(0, 200)) : '（空）';
    throw new Error(`无法识别所选文件夹的相对路径：读取到 ${files.length} 个文件，首个文件的 webkitRelativePath 为 ${sample}。请尝试拖拽文件夹上传，并反馈此信息。`);
  }
  return { name, entries: files.map(file => ({ file, path: file.webkitRelativePath.slice(name.length + 1) })) };
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
