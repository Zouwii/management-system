import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  createAITaskTicket,
  fetchTbcreateDraft,
  saveTbcreateDraft,
  initTbcreateWorkspace,
  fetchAITtydSession,
  fetchAIModels,
  fetchAIInsightList,
  fetchTbcreateTasks,
  syncKnowledgeBase,
  fetchAIKnowledgeTtydSession,
  createKnowledgeChatSession,
} from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import CollapsibleSection from '../components/CollapsibleSection';
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
  const [syncBusy, setSyncBusy] = useState(false);
  const [dashboardResult, setDashboardResult] = useState(null);
  const [dashboardError, setDashboardError] = useState('');
  const [expandedKeyword, setExpandedKeyword] = useState(null);

  // ── AI问答助手 ttyd ──
  const [kbTtydUrl, setKbTtydUrl] = useState('');
  const [kbTtydError, setKbTtydError] = useState('');
  const [kbTtydStarted, setKbTtydStarted] = useState(false);

  // ── 任务创建 ttyd 懒加载 ──
  const [tbTtydStarted, setTbTtydStarted] = useState(false);

  const startTbTtyd = useCallback(async () => {
    if (tbTtydStarted) return;
    setTbTtydStarted(true);
    try { await initTbcreateWorkspace(user, { ownerKey }); } catch {}
    try {
      const res = await fetchAITtydSession(user, { ownerKey, model: selectedModel || 'glm' });
      const url = String(res?.data?.embedUrl || '').trim();
      if (url) { setTtydUrl(url); setTtydError(''); }
      else { setTtydError('后端未返回 ttyd 地址'); }
    } catch (err) {
      setTtydError(err instanceof Error ? err.message : 'ttyd 初始化失败');
    }
  }, [ownerKey, selectedModel, user, tbTtydStarted]);

  const startKbTtyd = useCallback(async () => {
    if (kbTtydStarted || !selectedModel) return;
    setKbTtydStarted(true);
    try {
      const res = await fetchAIKnowledgeTtydSession(user, { ownerKey, model: selectedModel });
      const url = String(res?.data?.embedUrl || '').trim();
      if (url) { setKbTtydUrl(url); setKbTtydError(''); }
      else { setKbTtydError('后端未返回知识库 ttyd 地址'); }
    } catch (err) {
      setKbTtydError(err instanceof Error ? err.message : '知识库 ttyd 初始化失败');
    }
  }, [ownerKey, selectedModel, user, kbTtydStarted]);

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

  // ttyd sessions are now lazy-started via onToggle on each CollapsibleSection.

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
      return;
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
    try {
      setAnalysisStatus('拉取任务数据...');
      const t1 = await fetch('/api/bt/ai/task-analysis/fetch-tasks', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ quarter: '2026Q2', owner_key: ownerKey }),
        credentials: 'include',
      });
      const d1 = await t1.json();
      if (d1.code !== 200) throw new Error(d1.error || '步骤1失败');
      const { tasks, stats } = d1.data;

      setAnalysisStatus('检索知识库...');
      const t2 = await fetch('/api/bt/ai/task-analysis/search-kb', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tasks, generate: true }),
        credentials: 'include',
      });
      const d2 = await t2.json();
      if (d2.code !== 200) throw new Error(d2.error || '步骤2失败');

      setAnalysisStatus('LLM 分析中...');
      const t3 = await fetch('/api/bt/ai/task-analysis/generate-report', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tasks, stats, chunks: d2.data.chunks || [] }),
        credentials: 'include',
      });
      const d3 = await t3.json();
      if (d3.code !== 200) throw new Error(d3.error || '步骤3失败');

      setDashboardResult({ modules: d3.data, meta: { taskCount: stats.total_tasks }, stats });
      setAnalysisStatus(`分析完成（${stats.total_tasks}个任务）`);
    } catch (e) {
      setDashboardError(e.message || '分析失败');
      setAnalysisStatus('分析失败');
    } finally {
      setAnalysisBusy(false);
    }
  }, [ownerKey]);

  const handleSyncKnowledge = async () => {
    setSyncBusy(true);
    try {
      const res = await syncKnowledgeBase();
      if (res.code === 200) {
        const d = res.data;
        const sync = d.sync || {};
        const embed = d.embed || {};
        alert(
          `同步完成！\n` +
          `文档同步：${sync.totalSynced || d.totalSynced || '?'} 篇（变更 ${d.totalChanged || sync.totalSynced || '?'}）\n` +
          `切片重建：${d.rechunk?.chunkedDocs || '?'} 篇文档 → ${d.rechunk?.totalChunks || '?'} 个切片\n` +
          `向量生成：${embed.embedded || '?'} 个新向量（跳过 ${embed.skipped || '?'}）\n` +
          `总耗时：${d.durationSec || '?'}s`
        );
      } else {
        alert(`同步失败：${res.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`同步请求失败：${e.message}`);
    } finally {
      setSyncBusy(false);
    }
  };

  // ── SSE 知识库对话 ──
  const [chatSessionId, setChatSessionId] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const chatEsRef = useRef(null);

  useEffect(() => {
    let active = true;
    createKnowledgeChatSession()
      .then((res) => { if (active) setChatSessionId(res?.data?.sessionId || ''); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => () => { if (chatEsRef.current) { chatEsRef.current.close(); } }, []);

  const handleChatSend = useCallback(() => {
    const q = chatInput.trim();
    if (!q || chatBusy) return;
    setChatInput('');
    setChatBusy(true);
    setChatMessages((prev) => [...prev, { role: 'user', content: q }]);
    if (chatEsRef.current) { chatEsRef.current.close(); }
    const params = new URLSearchParams({ q });
    if (chatSessionId) params.set('session_id', chatSessionId);
    const es = new EventSource(`/api/bt/ai/knowledge/chat?${params.toString()}`);
    chatEsRef.current = es;
    let content = '';
    setChatMessages((prev) => [...prev, { role: 'assistant', content: '', citations: null }]);
    es.addEventListener('message', (e) => {
      let d;
      try { d = JSON.parse(e.data); } catch { return; }
      if (d.type === 'citation' && d.sources) {
        setChatMessages((prev) => { const n = [...prev]; const i = n.length-1; if (n[i]?.role === 'assistant') n[i] = {...n[i], citations: d.sources}; return n; });
      } else if (d.type === 'text' && d.content) {
        content += d.content;
        setChatMessages((prev) => { const n = [...prev]; const i = n.length-1; if (n[i]?.role === 'assistant') n[i] = {...n[i], content}; return n; });
      }
    });
    es.addEventListener('done', () => { es.close(); chatEsRef.current = null; setChatBusy(false); });
    es.onerror = () => { es.close(); chatEsRef.current = null; setChatBusy(false); };
  }, [chatInput, chatBusy, chatSessionId]);

  const handleChatKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatSend(); }
  }, [handleChatSend]);

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
      />

      <div className="space-y-4">
        {/* ═══════ AI 任务分析栏 ═══════ */}
        <CollapsibleSection
          defaultOpen={false}
          title="AI任务分析栏"
          extra={
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
              <button
                type="button"
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleSyncKnowledge}
                disabled={syncBusy}
              >
                {syncBusy ? '同步中...' : '同步知识库'}
              </button>
            </div>
          }
        >
          <div className="mt-2 space-y-5">
            <div className="rounded-[28px] border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-base font-semibold text-slate-900">根据工时进行分析</div>
                <span className="rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">工时</span>
              </div>
              <div className="mt-4">
                {analysisBusy && (
                  <div className="flex items-center justify-center gap-3 py-8 text-sm text-slate-500">
                    <svg className="h-5 w-5 animate-spin text-sky-500" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    AI 正在分析任务数据...
                  </div>
                )}
                {dashboardError && (
                  <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{dashboardError}</div>
                )}
                {!analysisBusy && !dashboardResult && (
                  <div className="py-8 text-center text-sm text-slate-400">
                    点击右上角"开始分析"按钮，AI 将拉取任务数据进行多维度分析
                  </div>
                )}
                {dashboardResult?.modules && (
                  <div className="grid gap-4 grid-cols-2">
                    {/* 1. 需求雷达 */}
                    <div className="rounded-xl border border-slate-200 bg-white border-l-4 border-l-sky-400 p-4 max-h-[260px] overflow-y-auto">
                      <div className="flex items-center gap-1.5 mb-2">
                        <svg className="h-4 w-4 text-sky-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                        <span className="text-xs font-semibold text-slate-800">需求雷达</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {(() => {
                          const keywords = dashboardResult.modules.requirement_radar?.keywords || [];
                          // 去重：同一词只保留首次出现
                          const seen = new Set();
                          const unique = keywords.filter(kw => {
                            const w = kw.word?.trim();
                            if (!w || seen.has(w)) return false;
                            seen.add(w);
                            return true;
                          });
                          return unique.slice(0, 10).map((kw, i) => (
                          <span key={i}
                            className={`rounded-lg px-3 py-1.5 text-sm font-medium cursor-pointer transition-colors ${
                              expandedKeyword === i
                                ? 'bg-sky-500 text-white shadow-sm'
                                : 'bg-sky-50 text-sky-700 hover:bg-sky-200 hover:text-sky-800'
                            }`}
                            onClick={() => setExpandedKeyword(expandedKeyword === i ? null : i)}>
                            {kw.word}
                          </span>
                        ));
                        })()}
                      </div>
                      {expandedKeyword !== null && (() => {
                        const kw = (dashboardResult.modules.requirement_radar?.keywords || [])[expandedKeyword];
                        return kw ? (
                          <div className="mt-2 rounded-lg border border-sky-100 bg-sky-50/50 p-3 text-sm space-y-1.5">
                            <div className="font-semibold text-slate-700">{kw.word}</div>
                            <div><span className="font-bold text-sky-600">存量挖掘</span>：{kw.suggestions?.dig_deeper || '-'}</div>
                            <div><span className="font-bold text-sky-600">质量升维</span>：{kw.suggestions?.quality_up || '-'}</div>
                            <div><span className="font-bold text-sky-600">前瞻探索</span>：{kw.suggestions?.look_forward || '-'}</div>
                          </div>
                        ) : null;
                      })()}
                    </div>

                    {/* 2. 自主型建议 */}
                    <div className="rounded-xl border border-slate-200 bg-white border-l-4 border-l-amber-400 p-4 max-h-[260px] overflow-y-auto">
                      <div className="flex items-center gap-1.5 mb-2">
                        <svg className="h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        <span className="text-xs font-semibold text-slate-800">自主型建议</span>
                      </div>
                      {(dashboardResult.modules.autonomous_suggestions?.suggestions || []).slice(0, 5).map((s, i) => (
                        <div key={i} className="rounded-lg border border-amber-100 bg-amber-50/50 p-2 mb-1.5 text-sm">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="font-medium text-slate-700">{s.source_task}</span>
                            <span className="rounded-full bg-amber-100 text-amber-700 px-1.5 py-0.5 text-xs font-bold">{s.priority_score || '-'}/10</span>
                          </div>
                          <div className="text-slate-500">{s.problem}</div>
                          <div className="text-amber-600 font-medium mt-1">{s.action}</div>
                          <div className="text-slate-400 mt-0.5">预估 {s.effort_days || '-'}d</div>
                        </div>
                      ))}
                    </div>

                    {/* 3. 任务分布与风险分析 */}
                    <div className="rounded-xl border border-slate-200 bg-white border-l-4 border-l-emerald-400 p-3 max-h-[260px] overflow-y-auto">
                      <div className="flex items-center gap-1.5 mb-2">
                        <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" /></svg>
                        <span className="text-xs font-semibold text-slate-800">任务分布与风险分析</span>
                      </div>
                      {(() => {
                        const tra = dashboardResult.modules.task_risk_analysis || {};
                        const st = dashboardResult.stats || {};
                        const aPct = Math.round(st.assigned_pct || 0);
                        const auPct = Math.round(st.autonomous_pct || 0);
                        const cPct = Math.round(st.capability_pct || 0);

                        const cone = `conic-gradient(#38bdf8 0deg ${aPct*3.6}deg, #a78bfa ${aPct*3.6}deg ${(aPct+auPct)*3.6}deg, #fb7185 ${(aPct+auPct)*3.6}deg 360deg)`;

                        return (
                          <div>
                            <div className="flex gap-3 mb-3">
                              <div className="flex items-start gap-2.5">
                                <div className="w-[100px] h-[100px] rounded-full flex-shrink-0 flex items-center justify-center" style={{ background: cone }}>
                                  <div className="w-[56px] h-[56px] rounded-full bg-white flex items-center justify-center">
                                    <span className="text-xs font-bold text-slate-500">占比</span>
                                  </div>
                                </div>
                                <div className="text-sm space-y-1 pt-1">
                                  <div className="flex items-center gap-1.5">
                                    <span className="w-2.5 h-2.5 rounded-sm bg-sky-400 flex-shrink-0"></span>
                                    <span className="text-slate-500">指派</span>
                                    <span className="font-semibold text-slate-700">{aPct}%</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="w-2.5 h-2.5 rounded-sm bg-violet-400 flex-shrink-0"></span>
                                    <span className="text-slate-500">自主</span>
                                    <span className="font-semibold text-slate-700">{auPct}%</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="w-2.5 h-2.5 rounded-sm bg-rose-400 flex-shrink-0"></span>
                                    <span className="text-slate-500">能力</span>
                                    <span className="font-semibold text-slate-700">{cPct}%</span>
                                  </div>
                                </div>
                              </div>
                              {/* 右上：工时天数 */}
                              <div className="flex-1 space-y-1 text-sm">
                                <div className="flex justify-between"><span className="text-slate-500">已排工时</span><span className="font-semibold">{st.quarter_work_hour || '-'}d</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">已完成</span><span className="font-semibold text-emerald-600">{st.quarter_completed_work_hour || '-'}d</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">至今预期</span><span className="font-semibold">{st.expected_hours_by_today || '-'}d</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">逾期工时</span><span className="font-semibold text-red-500">{st.quarter_overdue_work_hour || '0'}d</span></div>
                              </div>
                            </div>
                            {/* 下方：结论文字 */}
                            <div className="text-sm leading-relaxed text-slate-600 border-t border-slate-100 pt-2">
                              {tra.detail ? (
                                <div className="mb-1.5">{tra.detail}</div>
                              ) : (
                                <div className="mb-1.5 text-slate-400">暂无分析结论</div>
                              )}
                              {(tra.alerts || []).length > 0 && (
                                <div className="space-y-1">
                                  {(tra.alerts || []).map((al, i) => (
                                    <span key={i} className={`inline-block rounded px-1.5 py-0.5 mr-1.5 mb-1 text-xs font-medium ${al.level === 'red' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                                      {al.description}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })()}
                    </div>

                    {/* 4. 能力型建议 */}
                    <div className="rounded-xl border border-slate-200 bg-white border-l-4 border-l-violet-400 p-3 max-h-[260px] overflow-y-auto">
                      <div className="flex items-center gap-1.5 mb-2">
                        <svg className="h-4 w-4 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347" /></svg>
                        <span className="text-xs font-semibold text-slate-800">能力型建议</span>
                      </div>
                      {(dashboardResult.modules.capability_suggestions?.suggestions || []).slice(0, 4).map((s, i) => (
                        <div key={i} className="rounded-lg border border-violet-100 bg-violet-50/50 p-2 mb-1.5 text-sm">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="font-medium text-slate-700">{s.direction}</span>
                            <span className="rounded-full bg-violet-100 text-violet-700 px-1.5 py-0.5 text-xs font-bold">{s.priority_score || '-'}/10</span>
                          </div>
                          <div className="text-slate-500 mt-0.5">{s.reason}</div>
                          <div className="text-violet-700 bg-white rounded px-1.5 py-0.5 mt-1 font-medium">产出: {s.output_required}</div>
                          <div className="text-slate-400 mt-0.5">预估 {s.effort_days || '-'}d</div>
                        </div>
                      ))}
                    </div>

                  </div>
                )}
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
        </CollapsibleSection>

        {/* ═══════ AI 创建任务单 ═══════ */}
        <CollapsibleSection
          defaultOpen={false}
          title="AI创建任务单"
          onToggle={(open) => { if (open) startTbTtyd(); }}
        >
          <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(320px,0.88fr)_minmax(0,1.12fr)]">
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
        </CollapsibleSection>

        {/* ═══════ AI 问答助手 ═══════ */}
        <CollapsibleSection
          defaultOpen={false}
          title="AI问答助手"
          onToggle={(open) => { if (open) startKbTtyd(); }}
        >
          <div className="mt-2 flex min-h-[600px] flex-col rounded-[28px] border border-slate-200 bg-black p-2">
            {kbTtydUrl ? (
              <iframe
                title="AI knowledge base Q&A terminal"
                src={kbTtydUrl}
                className="h-full w-full min-h-[580px] rounded-[22px] border-0 bg-black"
              />
            ) : (
              <div className="flex h-full min-h-[580px] items-center justify-center rounded-[22px] border border-slate-800 bg-slate-950 px-4 text-sm text-slate-300">
                {kbTtydError || '知识库 ttyd 会话未就绪，请检查后端配置。'}
              </div>
            )}
          </div>
        </CollapsibleSection>

        {/* ═══════ SSE 知识库对话 ═══════ */}
        <CollapsibleSection
          defaultOpen={false}
          title="SSE 知识库对话"
        >
          <div className="mt-2 flex flex-col rounded-[28px] border border-slate-200 bg-white" style={{ minHeight: 480 }}>
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3" style={{ maxHeight: 380 }}>
              {chatMessages.length === 0 && (
                <div className="flex items-center justify-center h-32 text-sm text-slate-400">
                  在下方输入问题，AI 将基于知识库内容回答
                </div>
              )}
              {chatMessages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    msg.role === 'user' ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 border border-slate-100'
                  }`}>
                    <div className="whitespace-pre-wrap">{msg.content || (msg.role === 'assistant' && chatBusy && idx === chatMessages.length - 1 ? '思考中...' : '')}</div>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-slate-200">
                        <div className="text-xs font-medium text-slate-400 mb-1">参考来源：</div>
                        {msg.citations.map((c, ci) => (
                          <div key={ci} className="text-xs text-slate-400 truncate">{c.source} ({c.score.toFixed(3)})</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-slate-100 px-5 py-3">
              <div className="flex gap-2">
                <input type="text" className="flex-1 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:bg-white"
                  placeholder="输入问题，按 Enter 发送..." value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)} onKeyDown={handleChatKeyDown} disabled={chatBusy} />
                <button type="button" className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
                  onClick={handleChatSend} disabled={chatBusy || !chatInput.trim()}>
                  {chatBusy ? '...' : '发送'}
                </button>
              </div>
            </div>
          </div>
        </CollapsibleSection>
      </div>
    </EmployeeLayout>
  );
}
