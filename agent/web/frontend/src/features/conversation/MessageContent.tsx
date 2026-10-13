// Content rendering is deliberately plain text. Future formats can be added
// here without coupling them to session management or the event transport.
export function MessageContent({ content }: { content: string }) {
  return <div className="message-content">{content}</div>;
}
