import { useLayoutEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { QuestionAnswer } from '../../api/types';
import type { QuestionItem } from '../../state/conversation';

export function QuestionCard({ item, sessionId, disabled }: {
  item: QuestionItem; sessionId: string | null; disabled: boolean;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<QuestionAnswer | null>(null);
  const inFlight = useRef(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const answer = item.answer ?? accepted;
  const editable = item.status === 'pending' && !answer;
  const blocked = disabled || pending || !sessionId;
  useLayoutEffect(() => {
    const element = input.current;
    if (!element) return;
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight + 2, 160)}px`;
  }, [text, editable]);
  async function submit() {
    if (!editable || blocked || inFlight.current || (selected === null && !text.trim())) return;
    inFlight.current = true; setPending(true); setError(null);
    try {
      const result = await api.answerQuestion(sessionId!, item.questionId, {
        option_index: selected, text: selected === null ? text.trim() : '',
      });
      setAccepted(result.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '回答提交失败，请重试');
    } finally {
      inFlight.current = false; setPending(false);
    }
  }
  return <section className="question-card" aria-label="助手提问">
    <h3>{item.question}</h3>
    {editable ? <form onSubmit={event => { event.preventDefault(); void submit(); }}>
      {item.options.length > 0 && <div className="question-options" role="group" aria-label="回答选项">
        {item.options.map((option, index) => <button key={index} type="button" className="question-option"
          aria-pressed={selected === index} disabled={blocked}
          onClick={() => { setSelected(index); setText(''); setError(null); }}>
          <span className="question-number">{index + 1}</span>
          <span><span className="question-option-title">{option.title}</span>
            <span className="question-option-description">{option.description}</span></span>
        </button>)}
      </div>}
      <div className="question-actions"><textarea ref={input} aria-label={item.options.length ? '其他回答' : '你的回答'} maxLength={4000} rows={1}
        placeholder={item.options.length ? '或者，输入你的回答…' : '输入你的回答…'}
        disabled={blocked} value={text}
        onChange={event => { setText(event.target.value); setSelected(null); setError(null); }} />
      <button type="submit"
        disabled={blocked || (selected === null && !text.trim())}>{pending ? '提交中…' : '确认'}</button></div>
    </form> : <>
      <div className="question-answer-label">{answer ? '已回答' : '提问已取消'}</div>
      {answer && <div className="question-answer">{answer.text}</div>}
    </>}
    {error && <p className="question-error" role="alert">{error}</p>}
  </section>;
}
