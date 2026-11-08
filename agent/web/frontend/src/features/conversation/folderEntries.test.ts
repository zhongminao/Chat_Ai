import { describe, expect, it, vi } from 'vitest';
import { droppedAttachments, selectedFolder } from './folderEntries';

describe('folder attachments', () => {
  it('keeps nested relative paths when selecting a directory', () => {
    const files = [new File(['a'], 'a.txt'), new File(['b'], 'b.txt')];
    Object.defineProperty(files[0], 'webkitRelativePath', { value: 'project/a.txt' });
    Object.defineProperty(files[1], 'webkitRelativePath', { value: 'project/sub/b.txt' });
    expect(selectedFolder(files)).toEqual({ name: 'project', entries: [
      { file: files[0], path: 'a.txt' }, { file: files[1], path: 'sub/b.txt' },
    ] });
  });

  it('explains an empty folder selection instead of silently ignoring it', () => {
    expect(() => selectedFolder([])).toThrow('0 个文件');
  });

  it('reports the browser relative path when a selected folder cannot be recognized', () => {
    const file = new File(['a'], 'a.txt');
    expect(() => selectedFolder([file])).toThrow(/读取到 1 个文件.*webkitRelativePath 为 （空）/);
    Object.defineProperty(file, 'webkitRelativePath', { value: 'a.txt' });
    expect(() => selectedFolder([file])).toThrow(/webkitRelativePath 为 "a.txt"/);
  });

  it('reads all batches from a dropped directory, including nested files', async () => {
    const a = new File(['a'], 'a.txt');
    const b = new File(['b'], 'b.txt');
    const leaf = (file: File) => ({ name: file.name, isFile: true, isDirectory: false,
      file: (resolve: (value: File) => void) => resolve(file) });
    const directory = (name: string, batches: unknown[][]) => ({ name, isFile: false, isDirectory: true,
      createReader: () => ({ readEntries: (resolve: (value: unknown[]) => void) => resolve(batches.shift() ?? []) }) });
    const root = directory('project', [[leaf(a)], [directory('sub', [[leaf(b)]])], []]);
    const items = [{ kind: 'file', webkitGetAsEntry: () => root, getAsFile: vi.fn() }] as unknown as DataTransferItemList;
    const result = await droppedAttachments(items);
    expect(result).toEqual({ files: [], folders: [{ name: 'project', entries: [
      { file: a, path: 'a.txt' }, { file: b, path: 'sub/b.txt' },
    ] }] });
  });
});
