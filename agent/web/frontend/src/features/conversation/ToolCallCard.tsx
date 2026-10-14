import type { ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import type { ImageAsset } from '../../api/types';
import { ImageOutput } from '../images/ImageOutput';

const format = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
const labels = { running: '执行中', completed: '已完成', interrupted: '已中断' };

export function ToolCallCard({ item, sessionId, images = [] }: { item: ToolItem; sessionId?: string | null; images?: ImageAsset[] }) {
  return <div className="tool-output"><details className="tool-card">
    <summary><Icon name="tool" size={16} /><span className="tool-name">{item.name}</span>
      <span className={`tool-status ${item.status}`}>{labels[item.status]}</span><Icon name="down" size={14} /></summary>
    <div className="tool-body">
      {item.arguments !== undefined && <><div className="tool-label">调用参数</div><pre>{format(item.arguments)}</pre></>}
      {item.result !== undefined && <><div className="tool-label">工具结果</div><pre>{format(item.result)}</pre></>}
    </div>
  </details>
    {sessionId && item.images?.length ? <ImageOutput ids={item.images} assets={images} sessionId={sessionId} /> : null}
  </div>;
}
