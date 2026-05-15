import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  createAITaskTicket,
  fetchTbcreateDraft,
  saveTbcreateDraft,
  initTbcreateWorkspace,
  fetchAITtydSession,
  fetchAIModels,
  fetchAIInsightList,
  fetchTbcreateTasks,
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
    parentTaskId: String(draft.parentTaskId || fallback.parentTaskId || ''),
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
  const [taskList, setTaskList] = useState([]);
  const [parentSelectorOpen, setParentSelectorOpen] = useState(false);

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

  // Fetch all tasks for parent task selector
  useEffect(() => {
    let active = true;
    fetchTbcreateTasks(user, { ownerKey })
      .then((response) => { if (active) setTaskList(Array.isArray(response?.data) ? response.data : []); })
      .catch(() => {});
    return () => { active = false; };
  }, [ownerKey, user]);

  // SSE: auto-fetch draft when Claude writes/updates it
  useEffect(() => {
    if (!ownerKey) return;
    const url = `/api/bt/ai/tbcreate/draft/events?ownerKey=${encodeURIComponent(ownerKey)}`;
    const es = new EventSource(url);

    es.addEventListener('connected', () => {
      console.log('[sse] connected');
    });

    es.addEventListener('draft_updated', () => {
      fetchTbcreateDraft(user, { ownerKey })
        .then((response) => {
          const data = response?.data;
          if (data && typeof data === 'object') {
            setDraft((current) => normalizeDraft(data, current));
            setDraftStatus(data.title ? '草稿已更新' : '等待 Claude 写入草稿...');
          }
        })
        .catch((err) => console.error('[sse] fetch draft failed:', err));
    });

    es.onerror = () => {};

    return () => es.close();
  }, [ownerKey, user]);

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
        parentTaskId: draft.parentTaskId || undefined,
      });
      const result = response.data || {};
      // 从 taskUrl 提取 taskId 作为后备
      if (!result.taskId && result.taskUrl) {
        const match = String(result.taskUrl).match(/\/task\/([^/?#]+)/);
        if (match) result.taskId = match[1];
      }
      setCreateResult(result);
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

  // ── 产出天数校验 ─────────────────────────────────────────
  const outputDays = useMemo(() => {
    return draft.outputs
      .map((item) => {
        const match = String(item).match(/\(([\d.]+)天\)$/);
        return match ? parseFloat(match[1]) : NaN;
      })
      .filter((n) => Number.isFinite(n));
  }, [draft.outputs]);

  const sumOutputDays = useMemo(
    () => Math.round(outputDays.reduce((a, b) => a + b, 0) * 10) / 10,
    [outputDays],
  );

  const outputWarnings = useMemo(() => {
    const warnings = [];
    const count = draft.outputs.filter((item) => String(item).trim()).length;
    if (count > 5) {
      warnings.push('任务产出不能超过 5 条，请合并或删除多余的产出');
    }
    if (outputDays.length > 0) {
      if (!PARTICIPATION_LEVELS.includes(sumOutputDays)) {
        warnings.push(`产出工时合计 ${sumOutputDays} 天，与固定档位 ${PARTICIPATION_LEVELS.join('/')} 不匹配，请调整`);
      }
    }
    return warnings;
  }, [draft.outputs, outputDays, sumOutputDays]);

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
            </div>
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
            {/* Left panel: ttyd terminal */}
            <Card className="flex min-h-[760px] flex-col border-slate-200 bg-slate-50 p-5 shadow-none">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-900">AI 终端</div>
                </div>
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
                </div>
                <input
                  type="text"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xl font-semibold text-slate-900 outline-none transition focus:border-slate-300"
                  value={draft.title}
                  onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                  placeholder="等待 Claude 生成..."
                />
              </div>

              {/* 父任务 — 移到标题下方 */}
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">父任务（可选）</div>
                <div className="relative mt-2">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300"
                    onClick={() => setParentSelectorOpen((prev) => !prev)}
                  >
                    <span className={draft.parentTaskId ? '' : 'text-slate-400'}>
                      {draft.parentTaskId
                        ? (taskList.find((t) => t.taskId === draft.parentTaskId)?.title || draft.parentTaskId)
                        : '不选择父任务'}
                    </span>
                    <svg className={`h-4 w-4 text-slate-400 transition ${parentSelectorOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
                  </button>
                  {parentSelectorOpen && (
                    <div className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-lg">
                      <button
                        type="button"
                        className="w-full px-4 py-2.5 text-left text-sm text-slate-400 transition hover:bg-slate-50"
                        onClick={() => { setDraft((current) => ({ ...current, parentTaskId: '' })); setParentSelectorOpen(false); }}
                      >
                        不选择父任务
                      </button>
                      {taskList.map((item) => (
                        <button
                          key={item.taskId}
                          type="button"
                          className={`w-full px-4 py-2.5 text-left text-sm transition hover:bg-slate-50 ${draft.parentTaskId === item.taskId ? 'bg-sky-50 font-medium text-sky-700' : 'text-slate-700'}`}
                          onClick={() => { setDraft((current) => ({ ...current, parentTaskId: item.taskId })); setParentSelectorOpen(false); }}
                        >
                          <span className="line-clamp-1">{item.title}</span>
                          <span className="ml-2 text-xs text-slate-400">{item.taskId}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 起止时间 — 独立一行，横向排列 */}
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
                <textarea
                  className="mt-3 min-h-[120px] w-full resize-y rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-700 outline-none transition focus:border-slate-300"
                  value={draft.requirementDesc}
                  onChange={(event) => setDraft((current) => ({ ...current, requirementDesc: event.target.value }))}
                  placeholder="等待 Claude 填写..."
                />
              </div>

              <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-5">
                <div className="text-sm font-medium text-slate-500">任务产出</div>
                <div className="mt-3 space-y-2">
                  {draft.outputs.length > 0 ? (
                    draft.outputs.map((item, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="text"
                          className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-300"
                          value={item}
                          onChange={(event) => {
                            const next = [...draft.outputs];
                            next[idx] = event.target.value;
                            setDraft((current) => ({ ...current, outputs: next }));
                          }}
                        />
                        <button
                          type="button"
                          className="flex h-9 w-9 items-center justify-center rounded-full border border-red-200 text-red-400 transition hover:bg-red-50 hover:text-red-600"
                          onClick={() => {
                            const next = draft.outputs.filter((_, i) => i !== idx);
                            setDraft((current) => ({ ...current, outputs: next }));
                          }}
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="text-sm text-slate-400">等待 Claude 填写...</div>
                  )}
                  <button
                    type="button"
                    className="mt-2 flex items-center gap-1 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-500 transition hover:bg-slate-100"
                    onClick={() => setDraft((current) => ({ ...current, outputs: [...current.outputs, ''] }))}
                  >
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
                    添加产出
                  </button>
                </div>
              </div>

              {/* 底行：组合block(有效工时+参与度) | 操作 */}
              <div className="grid gap-4 sm:grid-cols-2">
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
                  <div className="mt-4 border-t border-slate-200 pt-4">
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
                  </div>
                </div>

                <div className="rounded-[28px] border border-slate-200 bg-white p-5">
                  {outputWarnings.length > 0 && (
                    <div className="mb-3 space-y-1">
                      {outputWarnings.map((w, i) => (
                        <div key={i} className="rounded-xl bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">{w}</div>
                      ))}
                    </div>
                  )}
                  <div className="text-sm font-medium text-slate-500">操作</div>
                  <div className="mt-4">
                    <button
                      type="button"
                      className="w-full rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={handleCreateTicket}
                      disabled={creating || !draft.title || draft.participationLevel <= 0 || outputWarnings.length > 0}
                    >
                      {creating ? '创建中...' : '创建 Teambition 任务单'}
                    </button>
                  </div>
                  {createResult ? (
                    <div className="mt-4 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                      <div className="font-semibold">{createResult.message}</div>
                      {createResult.taskUrl ? (
                        <div className="mt-1">
                          <a href={createResult.taskUrl} target="_blank" rel="noopener noreferrer" className="break-all text-emerald-700 underline hover:text-emerald-900">
                            任务链接：{createResult.taskUrl}
                          </a>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </EmployeeLayout>
  );
}
