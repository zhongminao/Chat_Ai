import type { GuidanceDraft } from './useGuidanceQueue';
import { Icon } from '../../ui/Icon';

export function GuidanceQueue({ items, disabled, canEdit, onGuide, onEdit, onRemove }: {
  items: GuidanceDraft[]; disabled: boolean; canEdit: boolean;
  onGuide: (item: GuidanceDraft) => void; onEdit: (item: GuidanceDraft) => void; onRemove: (id: string) => void;
}) {
  if (!items.length) return null;
  return <div className="guidance-queue" aria-label="前端引导队列">
    <ol className="guidance-queue-items">{items.map(item => <li className="guidance-draft" key={item.id}>
      <div className="guidance-draft-content">
        <span className="guidance-draft-text" title={item.text}>{item.text || '图片消息'}</span>
        {item.images.length > 0 && <span className="guidance-draft-images"><Icon name="image" size={13} />{item.images.length} 张图片</span>}
      </div>
      <div className="guidance-draft-actions">
        <button type="button" className="icon-button guidance-draft-send" aria-label="引导" title="引导"
          disabled={disabled} onClick={() => onGuide(item)}><Icon name="arrow" size={15} /><span>引导</span></button>
        <button type="button" className="icon-button guidance-draft-remove" aria-label="删除" title="删除"
          disabled={disabled} onClick={() => onRemove(item.id)}><Icon name="trash" size={15} /></button>
        <button type="button" className="icon-button" aria-label="编辑" disabled={disabled || !canEdit}
          title={canEdit ? '撤回输入框，重新发送后排到队尾' : '请先处理输入框中的内容'} onClick={() => onEdit(item)}><Icon name="edit" size={15} /></button>
      </div>
    </li>)}</ol>
  </div>;
}
