import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  createAITaskTicket,
  fetchTbcreateDraft,
  saveTbcreateDraft,
  initTbcreateWorkspace,
  fetchAITtydSession,
  fetchAIModels,
  fetchTbcreateTasks,
} from '../api/dashboard';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { useAuthStore } from '../store/authStore';
import AnalysisModules from './AnalysisModules';
import TaskCreatePanel from './TaskCreatePanel';

const PARTICIPATION_LEVELS = [0.2, 0.5, 1, 1.5, 2, 2.5, 3];
const WORK_TYPES = ['指派型', '自主型', '能力型'];

function getQuarterDateRange() {
  const now = new Date();
  const today = now.toISOString().slice(0, 10); // YYYY-MM-DD
  const month = now.getMonth(); // 0-indexed
  const year = now.getFullYear();

  // 季度末月份: Q1→2(Mar) Q2→5(Jun) Q3→8(Sep) Q4→11(Dec)
  const quarterEndMonth = Math.floor(month / 3) * 3 + 2;
  const lastDay = new Date(year, quarterEndMonth + 1, 0).toISOString().slice(0, 10);

  return { startDate: today, dueDate: lastDay };
}

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
    parentTaskId: String(draft.parentTaskId || ''),
  };
}

function resolveOwnerKey(user) {
  return String(user?.user_id || user?.userid || user?.name || 'anonymous');
}

export default function AIAnalysisPage() {
  const user = useAuthStore((state) => state.user);
  const ownerKey = resolveOwnerKey(user);
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
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [selectedModel, setSelectedModel] = useState('');
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const ttydCacheKey = `ai_ttyd_${ownerKey}_${selectedModel || 'config'}`;
  const [ttydUrl, setTtydUrl] = useState('');
  const [ttydError, setTtydError] = useState('');
  const [taskList, setTaskList] = useState([]);
  const [parentSelectorOpen, setParentSelectorOpen] = useState(false);
  const CACHE_TTL = 60 * 60 * 1000; // 1 hour
  const cacheKey = `ai_analysis_${ownerKey}`;
  const [dashboardResult, setDashboardResult] = useState(() => {
    try {
      const raw = sessionStorage.getItem(cacheKey);
      if (!raw) return null;
      const cached = JSON.parse(raw);
      if (cached.ts && Date.now() - cached.ts < CACHE_TTL) {
        return cached.data;
      }
      sessionStorage.removeItem(cacheKey);
      return null;
    } catch { return null; }
  });
  const [dashboardError, setDashboardError] = useState('');
  const [expandedKeyword, setExpandedKeyword] = useState(null);
  const [applyingKeys, setApplyingKeys] = useState(new Set());
  const [taskCreateHighlight, setTaskCreateHighlight] = useState(false);
  const [performanceOpen, setPerformanceOpen] = useState(false);
  const [performanceResult, setPerformanceResult] = useState(null);
  const [performanceError, setPerformanceError] = useState('');
  const taskCreateRef = useRef(null);

  // ── 任务创建 ttyd 懒加载 ──
  const [tbTtydStarted, setTbTtydStarted] = useState(false);

  const startTbTtyd = useCallback(async () => {
    if (!modelsLoaded) return;
    if (tbTtydStarted) return;
    setTbTtydStarted(true);

    try { await initTbcreateWorkspace(user, { ownerKey }); } catch {
      // The terminal session endpoint will surface configuration errors below.
    }
    try {
      const payload = selectedModel ? { ownerKey, model: selectedModel } : { ownerKey };
      const res = await fetchAITtydSession(user, payload);
      const url = String(res?.data?.embedUrl || '').trim();
      if (url) {
        setTtydUrl(url);
        setTtydError('');
      }
      else { setTtydError('后端未返回 ttyd 地址'); }
    } catch (err) {
      setTtydError(err instanceof Error ? err.message : 'ttyd 初始化失败');
    }
  }, [ownerKey, selectedModel, user, tbTtydStarted, modelsLoaded]);

  useEffect(() => {
    setTtydUrl('');
    setTtydError('');
    setTbTtydStarted(false);
    try { sessionStorage.removeItem(ttydCacheKey); } catch {}
  }, [ttydCacheKey]);

  useEffect(() => {
    startTbTtyd();
  }, [startTbTtyd]);


  // Load available AI models
  useEffect(() => {
    let active = true;
    fetchAIModels(user)
      .then((response) => {
        if (!active) return;
        const models = Array.isArray(response?.data?.models) ? response.data.models : [];
        setSelectedModel(models[0]?.name || '');
        setModelsLoaded(true);
      })
      .catch(() => {
        if (!active) return;
        setSelectedModel('');
        setModelsLoaded(true);
      });
    return () => { active = false; };
  }, [ownerKey, user]);

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
      setCreateResult(null);
      fetchTbcreateDraft(user, { ownerKey })
        .then((response) => {
          const data = response?.data;
          if (data && typeof data === 'object') {
            setDraft((current) => normalizeDraft(data, current));
          }
        })
        .catch((err) => console.error('[sse] fetch draft failed:', err));
    });

    es.onerror = () => {};

    return () => es.close();
  }, [ownerKey, user]);

  // Auto-save draft to backend when user edits fields (debounced 1s)
  useEffect(() => {
    if (!draft.title && draft.requirementDesc === 'Claude 正在等待你的输入。请在左侧终端中描述你的新任务。') {
      return;
    }
    const timer = window.setTimeout(() => {
      saveTbcreateDraft(user, { ownerKey, draft }).catch(() => {});
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [draft, ownerKey, user]);


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
      if (!result.taskId && result.taskUrl) {
        const match = String(result.taskUrl).match(/\/task\/([^/?#]+)/);
        if (match) result.taskId = match[1];
      }
      setCreateResult(result);
    } finally {
      setCreating(false);
    }
  };

  const handleAnalyze = useCallback(async () => {
    setAnalysisBusy(true);
    setDashboardResult(null);
    setDashboardError('');
    setPerformanceResult(null);
    setPerformanceError('');
    try {
      // 步骤1: 拉取任务数据
      const t1 = await fetch('/api/bt/ai/task-analysis/fetch-tasks', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ owner_key: ownerKey }),
        credentials: 'include',
      });
      const d1 = await t1.json();
      if (d1.code !== 200) throw new Error(d1.error || '步骤1失败');
      const { tasks, stats } = d1.data;

      // 步骤2 + 绩效分析：并行
      const [t2, tPerf] = await Promise.all([
        fetch('/api/bt/ai/task-analysis/search-kb', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ tasks, generate: true }),
          credentials: 'include',
        }),
        fetch('/api/bt/ai/task-analysis/performance-report', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ owner_key: ownerKey }),
          credentials: 'include',
        }),
      ]);
      const d2 = await t2.json();
      const dPerf = await tPerf.json();
      if (d2.code !== 200) throw new Error(d2.error || '步骤2失败');

      // 绩效结果
      if (dPerf.code === 200) {
        setPerformanceResult(dPerf.data);
      } else {
        setPerformanceError(dPerf.error || '绩效分析失败');
      }

      // 步骤3: 生成报告
      const t3 = await fetch('/api/bt/ai/task-analysis/generate-report', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tasks, stats, chunks: d2.data.chunks || [] }),
        credentials: 'include',
      });
      const d3 = await t3.json();
      if (d3.code !== 200) throw new Error(d3.error || '步骤3失败');

      const result = { modules: d3.data, meta: { taskCount: stats.total_tasks }, stats };
      setDashboardResult(result);
      try { sessionStorage.setItem(cacheKey, JSON.stringify({ data: result, ts: Date.now() })); } catch {}
    } catch (e) {
      setDashboardError(e.message || '分析失败');
    } finally {
      setAnalysisBusy(false);
    }
  }, [ownerKey]);

  const scrollToTaskCreate = useCallback(() => {
    window.setTimeout(() => {
      taskCreateRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTaskCreateHighlight(true);
      window.setTimeout(() => setTaskCreateHighlight(false), 1400);
    }, 80);
  }, []);

  const handleApplySuggestion = useCallback(async (suggestionType, suggestion, index) => {
    const key = `${suggestionType}-${index}`;
    setApplyingKeys((prev) => new Set(prev).add(key));
    try {
      const template = suggestion?.task_template || {};
      const workType = suggestionType === 'capability' || suggestionType === 'performance' ? '能力型' : '自主型';

      // Parse outputs: 优先 outputs 数组，兜底 output 字符串
      const templateOutputs = Array.isArray(template.outputs) ? template.outputs : [];
      let outputs;
      if (templateOutputs.length > 0) {
        outputs = templateOutputs.map((item) => String(item).trim()).filter(Boolean).slice(0, 5);
      } else {
        const outputStr = String(template.output || suggestion?.output_required || '').trim();
        outputs = outputStr
          ? outputStr.split(/\n|；|;/).map((item) => item.trim()).filter(Boolean).slice(0, 5)
          : [];
      }

      // Map effort_days to nearest participation level
      const effort = Number(suggestion?.effort_days);
      const participationLevel = PARTICIPATION_LEVELS.includes(effort)
        ? effort
        : PARTICIPATION_LEVELS.reduce((best, item) => (
          Math.abs(item - (Number.isFinite(effort) ? effort : 1)) < Math.abs(best - (Number.isFinite(effort) ? effort : 1)) ? item : best
        ), 1);

      const { startDate, dueDate } = getQuarterDateRange();

      let nextDraft;
      setDraft((current) => {
        nextDraft = {
          ...current,
          title: String(template.title || '').trim(),
          workType,
          requirementDesc: String(template.requirement_desc || '').trim(),
          outputs: outputs.length > 0 ? outputs : current.outputs,
          participationLevel,
          startDate,
          dueDate,
          parentTaskId: '',
        };
        return nextDraft;
      });

      setCreateResult(null);
      scrollToTaskCreate();

      if (nextDraft) {
        await saveTbcreateDraft(user, { ownerKey, draft: nextDraft });
      }
    } catch (err) {
      setDashboardError(err instanceof Error ? `生成草稿失败：${err.message}` : '生成草稿失败');
    } finally {
      setApplyingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }, [ownerKey, scrollToTaskCreate, user]);

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
      <div className="space-y-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.95fr)_minmax(460px,1.05fr)]">
          <section className="flex h-[calc(100vh-48px)] min-h-[720px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-3 border-b border-cyan-100 bg-cyan-50/80 px-4 py-3">
              <div className="flex items-center gap-2 text-base font-semibold leading-6 text-cyan-900">
                <span className="text-cyan-600">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </span>
                <span>AI任务分析栏</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="h-7 rounded-md bg-slate-900 px-3 text-[12px] font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={handleAnalyze}
                  disabled={analysisBusy}
                >
                  {analysisBusy ? '分析中' : '开始分析'}
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto bg-slate-50/60 p-3">
              <div className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-[14px] font-semibold leading-5 text-slate-900">根据工时进行分析</div>
                  <span className="rounded border border-cyan-100 bg-cyan-50 px-2 py-0.5 text-[12px] font-semibold text-cyan-700">工时</span>
                </div>
                {analysisBusy ? (
                  <div className="flex items-center justify-center gap-3 py-10 text-[13px] text-slate-500">
                    <svg className="h-4 w-4 animate-spin text-sky-500" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    AI 正在分析任务数据...
                  </div>
                ) : null}
                {dashboardError ? (
                  <div className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-[13px] text-red-700">{dashboardError}</div>
                ) : null}
                {!analysisBusy && !dashboardResult ? (
                  <div className="rounded-md border border-dashed border-slate-200 px-3 py-8 text-center text-[13px] text-slate-400">
                    点击“开始分析”，AI 将拉取任务数据进行多维度分析
                  </div>
                ) : null}
                {dashboardResult?.modules ? (
                  <AnalysisModules
                    dashboardResult={dashboardResult}
                    expandedKeyword={expandedKeyword}
                    setExpandedKeyword={setExpandedKeyword}
                    applyingKeys={applyingKeys}
                    handleApplySuggestion={handleApplySuggestion}
                  />
                ) : null}
              </div>

              <div className="mt-3 rounded-lg border border-slate-200 bg-white">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left transition hover:bg-slate-50"
                  onClick={() => setPerformanceOpen((open) => !open)}
                >
                  <div className="flex items-center gap-2">
                    <svg
                      className={`h-4 w-4 text-slate-400 transition-transform ${performanceOpen ? 'rotate-90' : ''}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2}
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                    </svg>
                    <div className="text-[14px] font-semibold leading-5 text-slate-900">根据绩效进行分析</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded border border-amber-100 bg-amber-50 px-2 py-0.5 text-[12px] font-semibold text-amber-700">绩效</span>
                  </div>
                </button>
                {performanceOpen ? (
                  <div className="border-t border-slate-100 p-3">
                    {analysisBusy && !performanceResult ? (
                      <div className="flex items-center justify-center gap-3 py-8 text-[13px] text-slate-500">
                        <svg className="h-4 w-4 animate-spin text-amber-500" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        AI 正在分析绩效数据...
                      </div>
                    ) : null}
                    {performanceError ? (
                      <div className="rounded-md border border-red-100 bg-red-50 px-3 py-2 text-[13px] text-red-700">{performanceError}</div>
                    ) : null}
                    {!analysisBusy && !performanceResult && !performanceError ? (
                      <div className="rounded-md border border-dashed border-slate-200 px-3 py-8 text-center text-[13px] text-slate-400">
                        点击上方"开始分析"，将同时拉取工时和绩效数据进行分析
                      </div>
                    ) : null}
                    {performanceResult ? (
                      <div className="grid gap-3 xl:grid-cols-2">
                        <StatusSummaryPanel data={performanceResult.status_summary} />
                        <SchedulingAdvicePanel data={performanceResult.scheduling_advice} />
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </section>

          <section
            ref={taskCreateRef}
            className={`flex h-[calc(100vh-48px)] min-h-[720px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white transition ${taskCreateHighlight ? 'ring-2 ring-indigo-300 ring-offset-2' : ''}`}
          >
            <div className="flex items-center justify-between gap-3 border-b border-indigo-100 bg-indigo-50/80 px-4 py-3">
              <div className="flex items-center gap-2 text-base font-semibold leading-6 text-indigo-900">
                <span className="text-indigo-600">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </span>
                <span>AI创建任务单</span>
              </div>
              <button
                type="button"
                className="h-7 rounded-md bg-slate-900 px-3 text-[12px] font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleCreateTicket}
                disabled={creating || !draft.title || draft.participationLevel <= 0 || outputWarnings.length > 0}
              >
                {creating ? '创建中...' : '创建任务单'}
              </button>
            </div>

            <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_380px]">
              <div className="min-h-0 overflow-y-auto border-b border-slate-200 bg-white p-3">
                <TaskCreatePanel
                  draft={draft}
                  setDraft={setDraft}
                  taskList={taskList}
                  parentSelectorOpen={parentSelectorOpen}
                  setParentSelectorOpen={setParentSelectorOpen}
                  outputWarnings={outputWarnings}
                  createResult={createResult}
                  WORK_TYPES={WORK_TYPES}
                  PARTICIPATION_LEVELS={PARTICIPATION_LEVELS}
                />
              </div>

              <div className="flex min-h-0 flex-col bg-[#1e1e1e] p-3">
                <div className="flex min-h-0 flex-1 flex-col rounded-md border border-slate-800 bg-black p-1.5">
                  {ttydUrl ? (
                    <iframe
                      title="AI ttyd terminal"
                      src={ttydUrl}
                      className="h-full w-full min-h-[328px] rounded border-0 bg-black"
                    />
                  ) : (
                    <div className="flex h-full min-h-[328px] items-center justify-center rounded border border-slate-800 bg-slate-950 px-4 text-[13px] text-slate-300">
                      {ttydError || 'AI 终端正在启动...'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </EmployeeLayout>
  );
}

// ── 绩效达标分析子组件 ────────────────────────────────────────

function StatusSummaryPanel({ data }) {
  const s = data || {};
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h3 className="mb-2 flex items-center gap-2 text-[13px] font-semibold leading-5 text-slate-800">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        达标现状
      </h3>
      {s.status ? (
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            {s.current_score != null ? (
              <span className="rounded bg-amber-50 px-2 py-1 text-[14px] font-bold text-amber-800">
                得分 {typeof s.current_score === 'number' ? s.current_score.toFixed(2) : s.current_score}
              </span>
            ) : null}
            {s.prev_carry != null && s.prev_carry > 0 ? (
              <span className="rounded bg-purple-50 px-2 py-1 text-[13px] font-semibold text-purple-700">
                上季结余 +{typeof s.prev_carry === 'number' ? s.prev_carry.toFixed(3) : s.prev_carry}
              </span>
            ) : null}
          </div>
          <p className="text-[13px] leading-5 text-slate-700">{(Array.isArray(s.status) ? s.status : [s.status]).map((line, i) => (
  <p key={i} className={'text-[13px] leading-5 ' + (i === 0 ? 'font-semibold text-slate-800' : 'text-slate-600')}>{line}</p>
))}</p>
        </div>
      ) : (
        <div className="text-[12px] text-slate-400">暂无分析结果</div>
      )}
    </section>
  );
}

function SchedulingAdvicePanel({ data }) {
  const advice = data || {};
  const suggestions = Array.isArray(advice.suggestions) ? advice.suggestions : [];
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h3 className="mb-2 flex items-center gap-2 text-[13px] font-semibold leading-5 text-slate-800">
        <span className="h-2 w-2 rounded-full bg-emerald-400" />
        排单建议
      </h3>
      {suggestions.length > 0 ? (
        <div className="divide-y divide-slate-100">
          {suggestions.map((item, i) => (
            <div key={i} className="py-2 first:pt-0 last:pb-0">
              <div className="flex items-start gap-2">
                <span className="shrink-0 mt-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-500">{item.priority || i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-semibold leading-5 text-slate-800">{item.direction}</div>
                  <div className="mt-0.5 text-[11px] leading-4 text-slate-500">{item.detail}</div>
                </div>
                {item.estimated_hours ? (
                  <span className="shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">+{item.estimated_hours}d</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-[12px] text-slate-400">暂无排单建议</div>
      )}
    </section>
  );
}
