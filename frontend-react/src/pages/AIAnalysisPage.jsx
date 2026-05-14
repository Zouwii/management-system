import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  createAITaskTicket,
  fetchTbcreateDraft,
  saveTbcreateDraft,
  initTbcreateWorkspace,
  fetchAITtydSession,
  fetchAIModels,
  fetchAIInsightList,
} from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { aiInsightList as fallbackData } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

const PARTICIPATION_LEVELS = [0.2, 0.5, 1, 1.5, 2, 2.5, 3];
const WORK_TYPES = ['指派型', '自主型', '能力型'];

function normalizeDraft(nextDraft, fallback) {
  const draft = nextDraft && typeof nextDraft === 'object' ? nextDraft : {};
  return {
    title: String(draft.title || fallback.title || ''),
    workType: WORK_TYPES.includes(draft.workType) ? draft.workType : fallback.workType,
    requirementDesc: String(draft.requirementDesc || fallback.requirementDesc || ''),
    outputs: Array.isArray(draft.outputs) && draft.outputs.length > 0 ? draft.outputs : fallback.outputs,
    participationLevel: PARTICIPATION_LEVELS.includes(Number(draft.participationLevel))
      ? Number(draft.participationLevel)
      : fallback.participationLevel,
    dueDate: String(draft.dueDate || fallback.dueDate || ''),
    startDate: String(draft.startDate || fallback.startDate || ''),
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
    title: '',
    workType: WORK_TYPES[0],
    requirementDesc: 'Claude 正在等待你的输入。请在左侧终端中描述你的新任务。',
    outputs: [],
    participationLevel: PARTICIPATION_LEVELS[0],
    dueDate: '',
    startDate: '',
  });
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState(null);
  const [analysisStatus, setAnalysisStatus] = useState('未分析');
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisInput, setAnalysisInput] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [ttydUrl, setTtydUrl] = useState('');
  const [ttydError, setTtydError] = useState('');
  const [draftStatus, setDraftStatus] = useState('等待 Claude 写入草稿...');
  const [draftSyncing, setDraftSyncing] = useState(false);

  // Load AI insights on mount
  useEffect(() => {
    let active = true;
    fetchAIInsightList().then((response) => {
      if (active) setInsights(response.data);
    });
    return () => { active = false; };
  }, []);

  // Load available AI models
  useEffect(() => {
    let active = true;
    fetchAIModels(user)
      .then((response) => {
        if (!active) return;
        const models = Array.isArray(response?.data?.models) ? response.data.models : [];
        setSelectedModel(models[0]?.name || 'glm');
      })
      .catch(() => {
        if (!active) return;
        setSelectedModel('glm');
      });
    return () => { active = false; };
  }, [ownerKey, user]);

  // Init workspace, then create ttyd session
  useEffect(() => {
    let active = true;

    async function initAndConnect() {
      // Step 1: initialize workspace (write context files)
      try {
        await initTbcreateWorkspace(user, { ownerKey });
      } catch {
        // Workspace init failure is non-fatal; ttyd session will fallback-init
      }

      if (!active) return;

      // Step 2: create ttyd session (starts Claude CLI in the workspace)
      try {
        const res = await fetchAITtydSession(user, { ownerKey, model: selectedModel || 'glm' });
        if (!active) return;
        const url = String(res?.data?.embedUrl || '').trim();
        if (!url) {
          setTtydUrl('');
          setTtydError('后端未返回 ttyd 地址，请检查 AI_TTYD_BASE_URL 配置。');
          return;
        }
        setTtydUrl(url);
        setTtydError('');
      } catch (err) {
        if (!active) return;
        setTtydUrl('');
        setTtydError(err instanceof Error ? err.message : 'ttyd 会话初始化失败');
      }
    }

    if (selectedModel) {
      initAndConnect();
    }

    return () => { active = false; };
  }, [ownerKey, selectedModel, user]);

  // Sync draft.json from the user's ttyd workspace (manual trigger)
  const handleSyncDraft = useCallback(async () => {
    setDraftSyncing(true);
    const startedAt = Date.now();
    try {
      const response = await fetchTbcreateDraft(user, { ownerKey });
      const data = response?.data;
      if (data && typeof data === 'object') {
        setDraft((current) => normalizeDraft(data, current));
        setDraftStatus(data.title ? '草稿已更新' : '等待 Claude 写入草稿...');
      } else {
        setDraftStatus('同步完成（草稿为空）');
      }
    } catch (err) {
      console.error('[sync-draft] failed:', err);
      setDraftStatus('同步失败');
    } finally {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, 400 - elapsed);
      window.setTimeout(() => setDraftSyncing(false), remaining);
    }
  }, [ownerKey, user]);

  // Auto-save draft to backend when user edits fields (debounced 1s)
  useEffect(() => {
    if (!draft.title && draft.requirementDesc === 'Claude 正在等待你的输入。请在左侧终端中描述你的新任务。') {
      return; // Skip initial empty state
    }
    const timer = window.setTimeout(() => {
      saveTbcreateDraft(user, { ownerKey, draft }).catch(() => {});
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [draft, ownerKey, user]);

  const hourInsights = useMemo(
    () => insights
      .filter((item) => item.type === '效率优化' || item.type === '负载预警')
      .map((item) => ({
        ...item,
        content: analysisInput
          ? `${item.content} 当前分析基于草稿重点："${analysisInput.slice(0, 36)}${analysisInput.length > 36 ? '...' : ''}"。`
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

  const handleCreateTicket = async () => {
    setCreating(true);
    try {
      const response = await createAITaskTicket(user, {
        title: draft.title,
        workType: draft.workType,
        requirementDesc: draft.requirementDesc,
        outputs: draft.outputs,
        participationLevel: draft.participationLevel,
        dueDate: draft.dueDate,
        startDate: draft.startDate,
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
        desc="左侧终端与 Claude 自然对话，Claude 写入 draft.json，右侧手动同步草稿。确认后创建正式任务单。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">AI 工作台</div>}
      />

      <div className="space-y-5">
        {/* AI Analysis Section */}
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

        {/* AI Task Creation Section */}
        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold text-slate-900">AI创建任务单</div>
              <div className="mt-1 text-sm text-slate-500">左侧终端与 Claude 对话，Claude 将草稿写入工作区，右侧面板可手动同步。</div>
            </div>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
              {draftStatus}
            </span>
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
            {/* Left panel: ttyd terminal */}
            <Card className="flex min-h-[760px] flex-col border-slate-200 bg-slate-50 p-5 shadow-none">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-900">AI 终端</div>
                  <div className="mt-1 text-sm text-slate-500">在终端里与 Claude 自然对话，描述你的新任务。</div>
                </div>
                <span className="rounded-full border border-sky-100 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
                  模型: {selectedModel || '...'}
                </span>
              </div>

              <div className="mt-4 flex flex-1 flex-col rounded-[28px] border border-slate-200 bg-black p-2">
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

            {/* Right panel: draft preview and controls */}
            <div className="space-y-4">
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-slate-500">任务标题</div>
                  <button
                    type="button"
                    className="flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
                    onClick={handleSyncDraft}
                    disabled={draftSyncing}
                  >
                    <svg className={`h-3.5 w-3.5 ${draftSyncing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
                    </svg>
                    {draftSyncing ? '同步中...' : '同步草稿'}
                  </button>
                </div>
                <div className="mt-2 text-xl font-semibold text-slate-900">{draft.title || '等待 Claude 生成...'}</div>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">有效工时类型</div>
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
                <div className="text-sm font-medium text-slate-500">起止时间</div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <div className="mb-1 text-xs text-slate-400">开始日期</div>
                    <input
                      type="date"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                      value={draft.startDate ? draft.startDate.slice(0, 10) : ''}
                      onChange={(event) => setDraft((current) => ({ ...current, startDate: event.target.value }))}
                    />
                  </div>
                  <div>
                    <div className="mb-1 text-xs text-slate-400">结束日期</div>
                    <input
                      type="date"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-900 outline-none transition focus:border-slate-300"
                      value={draft.dueDate ? draft.dueDate.slice(0, 10) : ''}
                      onChange={(event) => setDraft((current) => ({ ...current, dueDate: event.target.value }))}
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">需求描述</div>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">{draft.requirementDesc || '等待 Claude 填写...'}</div>
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务产出</div>
                <div className="mt-3 space-y-3">
                  {draft.outputs.length > 0 ? (
                    draft.outputs.map((item) => (
                      <div key={item} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="text-sm text-slate-400">等待 Claude 填写...</div>
                  )}
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
                  <div className="mt-4">
                    <button
                      type="button"
                      className="w-full rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={handleCreateTicket}
                      disabled={creating || !draft.title || draft.participationLevel <= 0}
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
