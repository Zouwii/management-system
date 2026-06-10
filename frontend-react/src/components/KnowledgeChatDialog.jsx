import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { createKnowledgeChatSession } from '../api/dashboard';

const suggestedQuestions = [
  '当前知识库有哪些可用资料？',
  '帮我查一下任务分析相关规则',
  '怎么根据工时分析生成任务单？',
];

export default function KnowledgeChatDialog({ open, onClose }) {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const esRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!open || sessionId) return undefined;
    let active = true;
    createKnowledgeChatSession()
      .then((res) => {
        if (active) setSessionId(res?.data?.sessionId || '');
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [open, sessionId]);

  useEffect(() => () => {
    if (esRef.current) esRef.current.close();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, status]);

  const handleSend = useCallback(() => {
    const question = input.trim();
    if (!question || busy) return;

    setInput('');
    setBusy(true);
    setStatus('准备连接知识库问答服务');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);

    if (esRef.current) esRef.current.close();
    const params = new URLSearchParams({ q: question });
    if (sessionId) params.set('session_id', sessionId);
    const es = new EventSource(`/api/bt/ai/knowledge/chat?${params.toString()}`);
    esRef.current = es;

    let content = '';
    setMessages((prev) => [...prev, { role: 'assistant', content: '', citations: null }]);

    es.addEventListener('message', (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }

      if (payload.type === 'citation' && payload.sources) {
        setMessages((prev) => {
          const next = [...prev];
          const index = next.length - 1;
          if (next[index]?.role === 'assistant') {
            next[index] = { ...next[index], citations: payload.sources };
          }
          return next;
        });
      } else if (payload.type === 'text' && payload.content) {
        content += payload.content;
        setStatus('');
        setMessages((prev) => {
          const next = [...prev];
          const index = next.length - 1;
          if (next[index]?.role === 'assistant') {
            next[index] = { ...next[index], content };
          }
          return next;
        });
      } else if (payload.type === 'status' && payload.content) {
        setStatus(payload.content);
      } else if (payload.type === 'error' && payload.content) {
        content += payload.content;
        setStatus('');
        setMessages((prev) => {
          const next = [...prev];
          const index = next.length - 1;
          if (next[index]?.role === 'assistant') {
            next[index] = { ...next[index], content };
          }
          return next;
        });
      }
    });

    es.addEventListener('done', () => {
      es.close();
      esRef.current = null;
      setBusy(false);
      setStatus('');
    });
    es.onerror = () => {
      es.close();
      esRef.current = null;
      setBusy(false);
      setStatus('');
    };
  }, [busy, input, sessionId]);

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/45 px-4 py-6 backdrop-blur-[2px]">
      <div className="flex h-[min(720px,88vh)] w-[min(900px,94vw)] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-[0_28px_90px_rgba(15,23,42,0.30)]">
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-purple-50 text-purple-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="text-[15px] font-semibold leading-5 text-slate-900">AI知识库问答</div>
              <div className="mt-0.5 text-[12px] leading-4 text-slate-500">本地 skill · 向量知识库 · 流式回答</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {busy ? (
              <span className="rounded-md border border-sky-100 bg-sky-50 px-2 py-1 text-[12px] font-medium text-sky-700">
                {status || '生成中'}
              </span>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-[18px] leading-none text-slate-500 transition hover:bg-slate-100"
              title="关闭"
            >
              x
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 px-4 py-4">
          {messages.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-[13px] font-semibold text-sky-700">
                  KB
                </div>
                <div className="min-w-0">
                  <div className="text-[15px] font-semibold leading-6 text-slate-900">
                    你好，我是知识库问答助手
                  </div>
                  <div className="mt-1 text-[13px] leading-6 text-slate-600">
                    你可以直接问内部文档、任务规则、工时分析、建单流程相关问题。我会先检索本地知识库，再给出带来源的回答。
                  </div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-[12px] leading-5 text-slate-600 transition hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700"
                    onClick={() => setInput(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="space-y-3">
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[82%] rounded-lg px-3 py-2 text-[13px] leading-6 shadow-sm ${
                  message.role === 'user'
                    ? 'bg-slate-900 text-white'
                    : 'border border-slate-200 bg-white text-slate-700'
                }`}>
                  <div className="whitespace-pre-wrap">
                    {message.content || (message.role === 'assistant' && busy && index === messages.length - 1 ? (status || '思考中...') : '')}
                  </div>
                  {message.citations?.length ? (
                    <div className="mt-2 border-t border-slate-200 pt-2 text-[12px] leading-5 text-slate-400">
                      <div className="font-medium text-slate-500">参考来源</div>
                      {message.citations.map((citation, citationIndex) => (
                        <div key={`${citation.chunk_id || citation.source}-${citationIndex}`} className="truncate">
                          {citation.source || '未知来源'}{Number.isFinite(citation.score) ? ` (${citation.score.toFixed(3)})` : ''}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            <div ref={scrollRef} />
          </div>
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3">
          <div className="flex gap-2">
            <textarea
              className="min-h-10 flex-1 resize-none rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[13px] leading-5 text-slate-900 outline-none transition focus:border-sky-300 focus:bg-white"
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={busy}
              rows={1}
            />
            <button
              type="button"
              className="h-10 rounded-md bg-slate-900 px-4 text-[13px] font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handleSend}
              disabled={busy || !input.trim()}
            >
              {busy ? '发送中' : '发送'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
