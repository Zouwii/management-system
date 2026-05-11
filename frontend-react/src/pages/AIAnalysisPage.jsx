import { useEffect, useMemo, useState } from 'react';
import {
  createAITaskTicket,
  confirmAITaskAssistantDraft,
  createAITaskAssistantConversation,
  fetchAITtydSession,
  fetchAIModels,
  fetchAIInsightList,
  sendAITaskAssistantMessage,
} from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { aiInsightList as fallbackData } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

const PARTICIPATION_LEVELS = [0.2, 0.5, 1, 1.5, 2, 2.5, 3];
const TASK_TYPES = ['方案设计任务', '开发实现任务', '系统联调任务'];
const WORK_TYPES = ['指派型', '自主型', '能力建设型'];

function normalizeDraft(nextDraft, fallback) {
  const draft = nextDraft && typeof nextDraft === 'object' ? nextDraft : {};
  return {
    title: String(draft.title || fallback.title || '待生成任务单'),
    taskType: TASK_TYPES.includes(draft.taskType) ? draft.taskType : fallback.taskType,
    workType: WORK_TYPES.includes(draft.workType) ? draft.workType : fallback.workType,
    requirementDesc: String(draft.requirementDesc || fallback.requirementDesc || ''),
    outputs: Array.isArray(draft.outputs) && draft.outputs.length > 0 ? draft.outputs : fallback.outputs,
    participationLevel: PARTICIPATION_LEVELS.includes(Number(draft.participationLevel))
      ? Number(draft.participationLevel)
      : fallback.participationLevel,
    missingFields: Array.isArray(draft.missingFields) ? draft.missingFields : [],
    confidence: Number(draft.confidence || 0),
  };
}

function resolveOwnerKey(user) {
  return String(user?.user_id || user?.userid || user?.name || 'anonymous');
}

export default function AIAnalysisPage() {
  const user = useAuthStore((state) => state.user);
  const ownerKey = resolveOwnerKey(user);
  const [insights, setInsights] = useState(fallbackData);
  const [draft, setDraft] = useState({
    title: '待生成任务单',
    taskType: TASK_TYPES[1],
    workType: WORK_TYPES[0],
    requirementDesc: '左侧和 AI 确认任务背景后，这里会生成需求描述。',
    outputs: ['待生成任务产出'],
    participationLevel: PARTICIPATION_LEVELS[0],
  });
  const [confirmed, setConfirmed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState(null);
  const [analysisStatus, setAnalysisStatus] = useState('未分析');
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisInput, setAnalysisInput] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [ttydUrl, setTtydUrl] = useState('');
  const [ttydError, setTtydError] = useState('');
  const [assistantConversation, setAssistantConversation] = useState(null);
  const [assistantMessages, setAssistantMessages] = useState([]);
  const [assistantInput, setAssistantInput] = useState('');
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [assistantError, setAssistantError] = useState('');
  const [savedDraft, setSavedDraft] = useState(null);

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
        setSelectedModel(fallback);
      })
      .catch(() => {
        if (!active) return;
        setSelectedModel('glm');
      });

    return () => {
      active = false;
    };
  }, [ownerKey, user]);

  useEffect(() => {
    let active = true;
    setAssistantBusy(true);
    setAssistantError('');
    createAITaskAssistantConversation(user)
      .then((response) => {
        if (!active) return;
        const conversation = response?.data || {};
        setAssistantConversation(conversation);
        setAssistantMessages(Array.isArray(conversation.messages) ? conversation.messages : []);
        if (conversation.draft) {
          setDraft((current) => normalizeDraft(conversation.draft, current));
        }
      })
      .catch((err) => {
        if (!active) return;
        setAssistantError(err instanceof Error ? err.message : 'AI 任务助手会话初始化失败');
      })
      .finally(() => {
        if (active) setAssistantBusy(false);
      });

    return () => {
      active = false;
    };
  }, [ownerKey, user]);

  const hourInsights = useMemo(
    () => insights
      .filter((item) => item.type === '效率优化' || item.type === '负载预警')
      .map((item) => ({
        ...item,
        content: analysisInput
          ? `${item.content} 当前分析基于草稿重点：“${analysisInput.slice(0, 36)}${analysisInput.length > 36 ? '...' : ''}”。`
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
          ? `${item.content} 当前判断已结合当前草稿里的任务背景和目标产出。`
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

  const handleSendAssistantMessage = async (event) => {
    event.preventDefault();
    const content = assistantInput.trim();
    const conversationId = assistantConversation?.id;
    if (!content || !conversationId || assistantBusy) return;

    setAssistantBusy(true);
    setAssistantError('');
    try {
      const response = await sendAITaskAssistantMessage(user, conversationId, content);
      const conversation = response?.data || {};
      setAssistantConversation(conversation);
      setAssistantMessages(Array.isArray(conversation.messages) ? conversation.messages : []);
      if (conversation.draft) {
        setDraft((current) => normalizeDraft(conversation.draft, current));
        setConfirmed(false);
        setSavedDraft(null);
      }
      setAssistantInput('');
    } catch (err) {
      setAssistantError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setAssistantBusy(false);
    }
  };

  const handleConfirmDraft = async () => {
    const conversationId = assistantConversation?.id;
    if (!conversationId) {
      setAssistantError('AI 会话还未初始化，暂时不能保存草稿');
      return;
    }
    setCreating(true);
    setAssistantError('');
    try {
      const response = await confirmAITaskAssistantDraft(user, conversationId, draft);
      setSavedDraft(response?.data || null);
      setConfirmed(true);
    } catch (err) {
      setAssistantError(err instanceof Error ? err.message : '保存临时草稿失败');
    } finally {
      setCreating(false);
    }
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
    const draftContext = [draft.title, draft.requirementDesc, ...draft.outputs]
      .map((item) => String(item || '').trim())
      .filter(Boolean)
      .join(' ');
    setAnalysisBusy(true);
    setAnalysisStatus('分析中...');

    window.setTimeout(() => {
      setAnalysisInput(draftContext);
      setAnalysisBusy(false);
      setAnalysisStatus(draftContext ? '已基于当前草稿更新' : '已按默认样例更新');
    }, 320);
  };

  return (
    <EmployeeLayout>
      <SectionTitle
        title="AI助理"
        desc="登录后读取当前用户任务，通过对话生成临时任务草稿，确认后再创建正式任务单。"
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
              <div className="mt-1 text-sm text-slate-500">系统先读取你的历史任务，再通过对话生成草稿；确认后先保存临时文件，后续可转正式任务单。</div>
            </div>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
              {confirmed ? '已保存临时草稿' : '待保存草稿'}
            </span>
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
            <Card className="flex min-h-[760px] flex-col border-slate-200 bg-slate-50 p-5 shadow-none">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-900">AI 对话</div>
                  <div className="mt-1 text-sm text-slate-500">先读取数据库任务，再引导你补充新任务描述。</div>
                </div>
                <span className="rounded-full border border-sky-100 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
                  {assistantConversation?.status === 'confirmed' ? '已确认' : '草稿中'}
                </span>
              </div>

              <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-sm font-semibold text-slate-900">任务上下文</div>
                <div className="mt-2 text-sm leading-6 text-slate-600">
                  {assistantConversation?.contextSummary || (assistantBusy ? '正在读取当前用户任务...' : '等待初始化')}
                </div>
                {assistantConversation?.contextMetrics ? (
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                    <div className="rounded-xl bg-slate-50 px-3 py-2">任务：{assistantConversation.contextMetrics.taskCount}</div>
                    <div className="rounded-xl bg-slate-50 px-3 py-2">未完成：{assistantConversation.contextMetrics.unfinishedTaskCount}</div>
                    <div className="rounded-xl bg-slate-50 px-3 py-2">已完成：{assistantConversation.contextMetrics.completedTaskCount}</div>
                    <div className="rounded-xl bg-slate-50 px-3 py-2">逾期：{assistantConversation.contextMetrics.overdueTaskCount}</div>
                  </div>
                ) : null}
              </div>

              <div className="mt-4 flex min-h-[300px] flex-1 flex-col rounded-2xl border border-slate-200 bg-white">
                <div className="flex-1 space-y-3 overflow-y-auto p-4">
                  {assistantMessages.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
                        message.role === 'user'
                          ? 'ml-8 bg-slate-900 text-white'
                          : 'mr-8 border border-slate-200 bg-slate-50 text-slate-700'
                      }`}
                    >
                      {message.content}
                    </div>
                  ))}
                  {assistantError ? (
                    <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {assistantError}
                    </div>
                  ) : null}
                </div>
                <form className="border-t border-slate-200 p-3" onSubmit={handleSendAssistantMessage}>
                  <textarea
                    className="h-24 w-full resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-900 outline-none transition focus:border-slate-400"
                    value={assistantInput}
                    onChange={(event) => setAssistantInput(event.target.value)}
                    placeholder="简单描述你想创建的任务，例如：帮我安排下周客户回访联调，产出联调记录和问题清单。"
                  />
                  <div className="mt-3 flex justify-end">
                    <button
                      type="submit"
                      className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={assistantBusy || !assistantInput.trim() || !assistantConversation?.id}
                    >
                      {assistantBusy ? '处理中...' : '发送并生成草稿'}
                    </button>
                  </div>
                </form>
              </div>

              <div className="mt-4 h-[260px] rounded-[28px] border border-slate-200 bg-black p-2">
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
            </Card>

            <div className="space-y-4">
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务标题</div>
                <div className="mt-2 text-xl font-semibold text-slate-900">{draft.title}</div>
                {draft.confidence ? (
                  <div className="mt-2 text-xs text-slate-500">草稿置信度：{Math.round(draft.confidence * 100)}%</div>
                ) : null}
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务类型</div>
                <select
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                  value={draft.taskType}
                  onChange={(event) => {
                    setConfirmed(false);
                    setSavedDraft(null);
                    setDraft((current) => ({ ...current, taskType: event.target.value }));
                  }}
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
                  onChange={(event) => {
                    setConfirmed(false);
                    setSavedDraft(null);
                    setDraft((current) => ({ ...current, workType: event.target.value }));
                  }}
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
                    onChange={(event) => {
                      setConfirmed(false);
                      setSavedDraft(null);
                      setDraft((current) => ({ ...current, participationLevel: Number(event.target.value) }));
                    }}
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
                      className="w-full rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={handleConfirmDraft}
                      disabled={creating || !assistantConversation?.id}
                    >
                      {creating ? '保存中...' : '保存临时草稿'}
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

              {savedDraft ? (
                <div className="rounded-[28px] border border-sky-100 bg-sky-50 p-5 text-sm text-sky-800">
                  <div className="font-semibold">{savedDraft.message || '已保存临时任务草稿'}</div>
                  <div className="mt-2 break-all">临时文件：{savedDraft.tempDraftPath}</div>
                </div>
              ) : null}

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
