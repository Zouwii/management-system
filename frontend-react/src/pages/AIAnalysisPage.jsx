import { useEffect, useMemo, useState } from 'react';
import {
  createAITaskTicket,
  endAIChatSession,
  fetchAITtydSession,
  fetchAIModels,
  fetchAIInsightList,
  sendAIChatSessionMessage,
  startAIChatSession,
} from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { aiInsightList as fallbackData } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

const PARTICIPATION_LEVELS = [0.2, 0.5, 1, 1.5, 2, 2.5, 3];
const TASK_TYPES = ['方案设计任务', '开发实现任务', '系统联调任务'];
const WORK_TYPES = ['指派型', '自主型', '能力建设型'];

function getTaskType(input) {
  if (input.includes('联调') || input.includes('协同') || input.includes('验证')) {
    return '系统联调任务';
  }

  if (input.includes('方案') || input.includes('设计') || input.includes('架构')) {
    return '方案设计任务';
  }

  return '开发实现任务';
}

function getWorkType(input) {
  if (input.includes('学习') || input.includes('调研') || input.includes('分享') || input.includes('PoC') || input.includes('Demo')) {
    return '能力建设型';
  }

  if (input.includes('优化') || input.includes('重构') || input.includes('复盘') || input.includes('补齐') || input.includes('脚本')) {
    return '自主型';
  }

  return '指派型';
}

function getParticipationLevel(input) {
  const score = Math.min(Math.max(Math.ceil((input.length || 18) / 18), 1), PARTICIPATION_LEVELS.length) - 1;
  return PARTICIPATION_LEVELS[score];
}

function buildAssistantReply(input, insights) {
  const normalizedInput = input.trim();
  const matchedInsights = insights
    .filter(() => normalizedInput.includes('工时') || normalizedInput.includes('绩效') || normalizedInput.length > 0)
    .slice(0, 2);

  const requirementDesc = normalizedInput || '补充任务背景后，AI 会自动整理需求描述。';
  const outputs = matchedInsights.length > 0
    ? matchedInsights.map((item) => `${item.title}对应的交付物整理`)
    : ['形成需求分析说明', '输出实施方案', '补充风险与验证记录'];
  const taskType = getTaskType(normalizedInput);
  const workType = getWorkType(normalizedInput);
  const participationLevel = getParticipationLevel(normalizedInput);

  return {
    summary: matchedInsights.length > 0
      ? matchedInsights.map((item) => item.content).join(' ')
      : '已根据当前对话整理任务背景，建议先补齐需求描述、任务产出和参与度评估。',
    requirementDesc,
    outputs,
    taskType,
    workType,
    participationLevel,
    title: `${(normalizedInput.split(/[，。；,\n]/)[0] || 'AI生成').slice(0, 18)}任务单`,
  };
}

function createConversationId() {
  return `ai-chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function resolveOwnerKey(user) {
  return String(user?.user_id || user?.userid || user?.name || 'anonymous');
}

function extractSessionReply(response) {
  const res = response?.data?.result;
  return String(
    res?.data?.result
    || res?.result
    || '',
  ).trim();
}

export default function AIAnalysisPage() {
  const user = useAuthStore((state) => state.user);
  const ownerKey = resolveOwnerKey(user);
  const [insights, setInsights] = useState(fallbackData);
  const [messages, setMessages] = useState([
    {
      id: 'assistant-default',
      role: 'assistant',
      content: '请描述任务背景和需要 AI 帮你补齐的内容。我会整理需求描述、任务产出、任务类型和参与度评估。',
    },
  ]);
  const [draft, setDraft] = useState({
    title: '待生成任务单',
    taskType: TASK_TYPES[1],
    workType: WORK_TYPES[0],
    requirementDesc: '左侧和 AI 确认任务背景后，这里会生成需求描述。',
    outputs: ['待生成任务产出'],
    participationLevel: PARTICIPATION_LEVELS[0],
  });
  const [input, setInput] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState(null);
  const [analysisStatus, setAnalysisStatus] = useState('未分析');
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisInput, setAnalysisInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState('');
  const [conversationId, setConversationId] = useState(() => createConversationId());
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [chatViewMode, setChatViewMode] = useState('chat');
  const [ttydUrl, setTtydUrl] = useState('');
  const [ttydError, setTtydError] = useState('');

  useEffect(() => {
    let active = true;

    fetchAIInsightList().then((response) => {
      if (active) {
        setInsights(response.data);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fetchAIModels(user)
      .then((response) => {
        if (!active) return;
        const models = Array.isArray(response?.data?.models) ? response.data.models : [];
        const fallback = models[0]?.name || 'glm';
        setAvailableModels(models);
        setSelectedModel(fallback);
        return startAIChatSession(user, { ownerKey }).then((startRes) => {
          if (!active) return;
          const welcome = extractSessionReply(startRes) || `AI 已就绪，当前模型：${fallback}。`;
          const nextConversationId = String(startRes?.data?.conversationId || conversationId || '');
          if (nextConversationId) {
            setConversationId(nextConversationId);
          }
          setMessages([
            {
              id: 'assistant-ready',
              role: 'assistant',
              content: welcome,
            },
          ]);
        });
      })
      .catch(() => {
        if (!active) return;
        setAvailableModels([{ name: 'glm', description: '默认模型' }]);
        setSelectedModel('glm');
        setMessages([
          {
            id: 'assistant-ready-fallback',
            role: 'assistant',
            content: 'AI 已就绪，当前模型：glm。请直接输入问题。',
          },
        ]);
      });

    return () => {
      active = false;
    };
  }, [conversationId, ownerKey, user]);

  useEffect(() => () => {
    endAIChatSession(user, { ownerKey }).catch(() => {});
  }, [conversationId, ownerKey, user]);

  const hourInsights = useMemo(
    () => insights
      .filter((item) => item.type === '效率优化' || item.type === '负载预警')
      .map((item) => ({
        ...item,
        content: analysisInput
          ? `${item.content} 当前分析基于对话重点：“${analysisInput.slice(0, 36)}${analysisInput.length > 36 ? '...' : ''}”。`
          : item.content,
      })),
    [analysisInput, insights],
  );
  const performanceInsights = useMemo(
    () => insights
      .filter((item) => item.type === '绩效关联' || item.type === '能力发展')
      .map((item) => ({
        ...item,
        content: analysisInput
          ? `${item.content} 当前判断已结合本次对话里的任务背景和目标产出。`
          : item.content,
      })),
    [analysisInput, insights],
  );

  useEffect(() => {
    let active = true;
    fetchAITtydSession(user, { ownerKey, model: selectedModel || 'glm' })
      .then((res) => {
        if (!active) return;
        const url = String(res?.data?.embedUrl || '').trim();
        if (!url) {
          setTtydUrl('');
          setTtydError('后端未返回 ttyd 地址，请检查 AI_TTYD_BASE_URL 配置。');
          return;
        }
        setTtydUrl(url);
        setTtydError('');
        setChatViewMode((prev) => (prev === 'chat' ? 'ttyd' : prev));
      })
      .catch((err) => {
        if (!active) return;
        setTtydUrl('');
        setTtydError(err instanceof Error ? err.message : 'ttyd 会话初始化失败');
      });
    return () => {
      active = false;
    };
  }, [ownerKey, selectedModel, user]);

  const handleSend = async () => {
    const value = input.trim();
    if (!value || chatSending) {
      return;
    }

    const userMessage = { id: `${Date.now()}-user`, role: 'user', content: value };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setChatError('');
    setChatSending(true);

    let aiReply = '';
    try {
      const response = await sendAIChatSessionMessage(user, { prompt: value, ownerKey });
      aiReply = extractSessionReply(response);
      const nextConversationId = String(response?.data?.conversationId || conversationId || '');
      if (nextConversationId) {
        setConversationId(nextConversationId);
      }
      if (!aiReply) {
        aiReply = 'AI 暂未返回有效结果，请稍后重试。';
      }
    } catch (error) {
      aiReply = '请求 AI 失败（可能超时），请重试或缩短问题后再试。';
      setChatError(error instanceof Error ? error.message : '请求 AI 失败');
    } finally {
      setChatSending(false);
    }

    const reply = buildAssistantReply(value, insights);
    setMessages((current) => [
      ...current,
      { id: `${Date.now()}-assistant`, role: 'assistant', content: aiReply },
    ]);
    setDraft(reply);
    setConfirmed(false);
    setCreateResult(null);
  };

  const handleConfirmDraft = () => {
    setConfirmed(true);
    setMessages((current) => [
      ...current,
      {
        id: `${Date.now()}-confirm`,
        role: 'assistant',
        content: '已确认当前任务草稿，可以继续创建 Teambition 任务单。',
      },
    ]);
  };

  const handleCreateTicket = async () => {
    setCreating(true);

    try {
      const response = await createAITaskTicket(user, {
        title: draft.title,
        taskType: draft.taskType,
        workType: draft.workType,
        requirementDesc: draft.requirementDesc,
        outputs: draft.outputs,
        participationLevel: draft.participationLevel,
      });

      setCreateResult(response.data);
    } finally {
      setCreating(false);
    }
  };

  const handleAnalyze = () => {
    const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user')?.content ?? '';
    setAnalysisBusy(true);
    setAnalysisStatus('分析中...');

    window.setTimeout(() => {
      setAnalysisInput(lastUserMessage);
      setAnalysisBusy(false);
      setAnalysisStatus(lastUserMessage ? '已基于当前对话更新' : '已按默认样例更新');
    }, 320);
  };

  return (
    <EmployeeLayout>
      <SectionTitle
        title="AI助理"
        desc="通过左侧对话确认任务背景，右侧同步生成 AI 分析、需求描述、任务产出、任务类型和参与度评估。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">AI 工作台</div>}
      />

      <div className="space-y-5">
        <Card className="p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-lg font-semibold text-slate-900">AI任务分析栏</div>
              <div className="mt-1 text-sm text-slate-500">根据工时和绩效两条线，给出与当前任务背景相关的执行建议。</div>
            </div>
            <div className="flex items-center gap-3">
              <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">{analysisStatus}</div>
              <button
                type="button"
                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleAnalyze}
                disabled={analysisBusy}
              >
                {analysisBusy ? '分析中...' : '开始分析'}
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-base font-semibold text-slate-900">根据工时进行分析</div>
                <span className="rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">工时</span>
              </div>
              <div className="mt-4 space-y-3">
                {hourInsights.map((item) => (
                  <div key={item.title} className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                    <div className="text-sm font-semibold text-slate-900">{item.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-600">{item.content}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-base font-semibold text-slate-900">根据绩效进行分析</div>
                <span className="rounded-full border border-amber-100 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">绩效</span>
              </div>
              <div className="mt-4 space-y-3">
                {performanceInsights.map((item) => (
                  <div key={item.title} className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                    <div className="text-sm font-semibold text-slate-900">{item.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-600">{item.content}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold text-slate-900">AI创建任务单</div>
              <div className="mt-1 text-sm text-slate-500">通过左侧对话确认任务背景，右侧生成任务字段，确认后可调用 Teambition 接口创建任务。</div>
            </div>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
              {confirmed ? '已确认草稿' : '待确认草稿'}
            </span>
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
            <Card className="flex min-h-[760px] flex-col border-slate-200 bg-slate-50 p-5 shadow-none">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-900">AI 对话</div>
                  <div className="mt-1 text-sm text-slate-500">
                    {chatViewMode === 'ttyd'
                      ? '终端模式：直接在 ttyd 子窗口里与 AI 交互。'
                      : '先和 AI 确认任务背景，再决定是否生成任务单。'}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      chatViewMode === 'chat'
                        ? 'border border-slate-200 bg-white text-slate-900'
                        : 'border border-slate-200 bg-slate-50 text-slate-500 hover:text-slate-700'
                    }`}
                    onClick={() => setChatViewMode('chat')}
                  >
                    聊天模式
                  </button>
                  <button
                    type="button"
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      chatViewMode === 'ttyd'
                        ? 'border border-sky-100 bg-sky-50 text-sky-700'
                        : 'border border-slate-200 bg-slate-50 text-slate-500 hover:text-slate-700'
                    }`}
                    onClick={() => setChatViewMode('ttyd')}
                    title={ttydUrl ? '切换到 ttyd 终端模式' : (ttydError || 'ttyd 未就绪')}
                  >
                    ttyd模式
                  </button>
                </div>
              </div>

              {chatViewMode === 'ttyd' ? (
                <div className="mt-5 h-[560px] rounded-[28px] border border-slate-200 bg-black p-2">
                  {ttydUrl ? (
                    <iframe
                      title="AI ttyd terminal"
                      src={ttydUrl}
                      className="h-full w-full rounded-[22px] border-0 bg-black"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center rounded-[22px] border border-slate-800 bg-slate-950 px-4 text-sm text-slate-300">
                      {ttydError || 'ttyd 会话未就绪，请检查后端 AI_TTYD_BASE_URL / AI_TTYD_PORT_BASE 配置。'}
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div
                    className="mt-5 h-[420px] space-y-3 overflow-y-auto rounded-[28px] border border-slate-200 bg-white p-4"
                    style={{ scrollbarWidth: 'thin' }}
                  >
                    {messages.map((message) => (
                      <div
                        key={message.id}
                        className={`max-w-[88%] rounded-3xl px-4 py-3 text-sm leading-6 ${
                          message.role === 'user'
                            ? 'ml-auto bg-slate-900 text-white'
                            : 'border border-slate-200 bg-slate-50 text-slate-700'
                        }`}
                      >
                        {message.content}
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 rounded-[28px] border border-slate-200 bg-white p-4">
                    <textarea
                      className="min-h-[120px] max-h-[280px] w-full resize-y bg-transparent text-sm leading-6 text-slate-700 outline-none"
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault();
                          handleSend();
                        }
                      }}
                      placeholder="例如：我需要创建一个多段虚拟规划算法实车测试任务，需要产出测试说明、结果结论，并评估实际有效工时。"
                    />
                    {chatError ? (
                      <div className="mt-2 text-xs text-rose-500">
                        AI 调用失败：{chatError}
                      </div>
                    ) : null}
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        type="button"
                        className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={handleSend}
                        disabled={chatSending || !input.trim()}
                      >
                        {chatSending ? '发送中...' : '发送给 AI'}
                      </button>
                      <button
                        type="button"
                        className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                        onClick={() => {
                          endAIChatSession(user, { ownerKey }).catch(() => {});
                          const nextConversationId = createConversationId();
                          setConversationId(nextConversationId);
                          setSelectedModel(availableModels[0]?.name || 'glm');
                          setInput('');
                          setMessages([{ id: 'assistant-ready-reset', role: 'assistant', content: '正在重启 AI 会话...' }]);
                          setDraft({
                            title: '待生成任务单',
                            taskType: TASK_TYPES[1],
                            workType: WORK_TYPES[0],
                            requirementDesc: '左侧和 AI 确认任务背景后，这里会生成需求描述。',
                            outputs: ['待生成任务产出'],
                            participationLevel: PARTICIPATION_LEVELS[0],
                          });
                          setConfirmed(false);
                          setCreateResult(null);
                        }}
                      >
                        重置对话
                      </button>
                    </div>
                  </div>
                </>
              )}
            </Card>

            <div className="space-y-4">
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务标题</div>
                <div className="mt-2 text-xl font-semibold text-slate-900">{draft.title}</div>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务类型</div>
                <select
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                  value={draft.taskType}
                  onChange={(event) => setDraft((current) => ({ ...current, taskType: event.target.value }))}
                >
                  {TASK_TYPES.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">工时类型</div>
                <select
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                  value={draft.workType}
                  onChange={(event) => setDraft((current) => ({ ...current, workType: event.target.value }))}
                >
                  {WORK_TYPES.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">需求描述</div>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{draft.requirementDesc}</div>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务产出</div>
                <div className="mt-3 space-y-3">
                  {draft.outputs.map((item) => (
                    <div key={item} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(260px,0.85fr)]">
                <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                  <div className="text-sm font-medium text-slate-500">参与度评估（人天）</div>
                  <select
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                    value={draft.participationLevel}
                    onChange={(event) => setDraft((current) => ({ ...current, participationLevel: Number(event.target.value) }))}
                  >
                    {PARTICIPATION_LEVELS.map((item) => (
                      <option key={item} value={item}>{item} 人天</option>
                    ))}
                  </select>
                  <div className="mt-2 text-sm leading-6 text-slate-500">按固定档位评估：0.2 / 0.5 / 1 / 1.5 / 2 / 2.5 / 3，单任务原则上不超过 3。</div>
                </div>

                <div className="rounded-[28px] border border-slate-200 bg-white p-5">
                  <div className="text-sm font-medium text-slate-500">操作</div>
                  <div className="mt-4 space-y-3">
                    <button
                      type="button"
                      className="w-full rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
                      onClick={handleConfirmDraft}
                    >
                      确认当前草稿
                    </button>
                    <button
                      type="button"
                      className="w-full rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={handleCreateTicket}
                      disabled={!confirmed || creating || draft.participationLevel <= 0}
                    >
                      {creating ? '创建中...' : '创建 Teambition 任务单'}
                    </button>
                  </div>
                </div>
              </div>

              {createResult ? (
                <div className="rounded-[28px] border border-emerald-100 bg-emerald-50 p-5 text-sm text-emerald-800">
                  <div className="font-semibold">{createResult.message}</div>
                  <div className="mt-2">任务编号：{createResult.taskId}</div>
                  <div className="mt-1 break-all">任务链接：{createResult.taskUrl}</div>
                </div>
              ) : null}
            </div>
          </div>
        </Card>
      </div>
    </EmployeeLayout>
  );
}
