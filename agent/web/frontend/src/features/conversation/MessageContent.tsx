import { memo } from 'react';
import { MarkdownContent } from './content/MarkdownContent';
import { useStreamingText } from './content/useStreamingText';

export const MessageContent = memo(function MessageContent({ content, role, streaming = false }: {
  content: string; role: 'user' | 'assistant'; streaming?: boolean;
}) {
  const shown = useStreamingText(content, role === 'assistant' && streaming);
  return role === 'assistant'
    ? <MarkdownContent content={shown} />
    : <div className="message-content">{content}</div>;
});
