import { useState } from 'react';

const ITEMS_PER_PAGE = 3;

function uniqueKeywords(keywords = []) {
  const seen = new Set();
  return keywords.filter((kw) => {
    const word = String(kw?.word || '').trim();
    if (!word || seen.has(word)) return false;
    seen.add(word);
    return true;
  });
}

function ModulePanel({ title, tone = 'sky', actions, children }) {
  const toneMap = {
    sky: 'border-l-sky-400',
    amber: 'border-l-amber-400',
    emerald: 'border-l-emerald-400',
    violet: 'border-l-violet-400',
  };
  return (
    <section className={`min-h-[220px] overflow-hidden rounded-lg border border-slate-200 bg-white border-l-4 ${toneMap[tone]}`}>
      <div className="flex h-9 items-center justify-between border-b border-slate-100 px-3">
        <h3 className="text-[13px] font-semibold leading-5 text-slate-800">{title}</h3>
        {actions}
      </div>
      <div className="max-h-[292px] overflow-y-auto px-3 py-3">{children}</div>
    </section>
  );
}

function ApplyButton({ disabled, onClick }) {
  return (
    <button
      type="button"
      className="group flex h-7 shrink-0 items-center gap-1.5 rounded-full px-1.5 pr-2 text-[12px] font-medium text-slate-400 transition hover:bg-slate-100 hover:text-emerald-600 disabled:cursor-not-allowed disabled:bg-emerald-50 disabled:text-emerald-600"
      onClick={onClick}
      disabled={disabled}
      title="采纳建议"
      aria-label="采纳建议"
    >
      <span className="relative flex h-6 w-6 items-center justify-center rounded-full transition-colors duration-300 group-hover:bg-white/70">
        <svg
          className={`absolute h-5 w-5 text-slate-300 transition-all duration-300 ease-in-out ${
            disabled ? 'scale-75 -rotate-45 opacity-0' : 'scale-100 rotate-0 opacity-100 group-hover:scale-75 group-hover:-rotate-45 group-hover:opacity-0'
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <svg
          className={`absolute h-5 w-5 text-emerald-500 drop-shadow-sm transition-all duration-300 ease-out ${
            disabled ? 'scale-100 rotate-0 opacity-100' : 'scale-50 -rotate-45 opacity-0 group-hover:scale-100 group-hover:rotate-0 group-hover:opacity-100'
          }`}
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <path fillRule="evenodd" clipRule="evenodd" d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22ZM16.7071 9.70711C17.0976 9.31658 17.0976 8.68342 16.7071 8.29289C16.3166 7.90237 15.6834 7.90237 15.2929 8.29289L10.5 13.0858L8.70711 11.2929C8.31658 10.9024 7.68342 10.9024 7.29289 11.2929C6.90237 11.6834 6.90237 12.3166 7.29289 12.7071L9.79289 15.2071C10.1834 15.5976 10.8166 15.5976 11.2071 15.2071L16.7071 9.70711Z" />
        </svg>
      </span>
      <span className="transition-colors duration-300">采纳</span>
    </button>
  );
}

const keywordTones = [
  {
    dot: 'bg-rose-500',
    bar: 'bg-rose-400',
    row: 'text-rose-700 hover:bg-rose-50',
    activeRow: 'bg-rose-50 text-rose-800',
    badge: 'border-rose-200 bg-rose-50 text-rose-700',
  },
  {
    dot: 'bg-amber-500',
    bar: 'bg-amber-400',
    row: 'text-amber-700 hover:bg-amber-50',
    activeRow: 'bg-amber-50 text-amber-800',
    badge: 'border-amber-200 bg-amber-50 text-amber-700',
  },
  {
    dot: 'bg-sky-500',
    bar: 'bg-sky-400',
    row: 'text-sky-700 hover:bg-sky-50',
    activeRow: 'bg-sky-50 text-sky-800',
    badge: 'border-sky-200 bg-sky-50 text-sky-700',
  },
  {
    dot: 'bg-slate-400',
    bar: 'bg-slate-300',
    row: 'text-slate-600 hover:bg-slate-50',
    activeRow: 'bg-slate-50 text-slate-800',
    badge: 'border-slate-200 bg-slate-50 text-slate-600',
  },
];

function keywordTone(index) {
  return keywordTones[index % keywordTones.length];
}

export default function AnalysisModules({
  dashboardResult,
  expandedKeyword,
  setExpandedKeyword,
  applyingKeys,
  handleApplySuggestion,
}) {
  const modules = dashboardResult?.modules || {};
  const stats = dashboardResult?.stats || {};
  const keywords = uniqueKeywords(modules.requirement_radar?.keywords || []).slice(0, 10);
  const activeKeywordIndex = keywords.length > 0 && expandedKeyword !== null && keywords[expandedKeyword] ? expandedKeyword : 0;
  const selectedKeyword = keywords[activeKeywordIndex] || null;
  const selectedTone = keywordTone(activeKeywordIndex);

  // ── Pagination state ──────────────────────────────────────────
  const allAutonomous = modules.autonomous_suggestions?.suggestions || [];
  const allCapability = modules.capability_suggestions?.suggestions || [];
  const risk = modules.task_risk_analysis || {};

  const autoSignature = allAutonomous.map((item) => JSON.stringify(item)).join('|');
  const capSignature = allCapability.map((item) => JSON.stringify(item)).join('|');
  const [autoPagination, setAutoPagination] = useState({ signature: autoSignature, page: 0 });
  const [capPagination, setCapPagination] = useState({ signature: capSignature, page: 0 });

  const autoPages = Math.max(1, Math.ceil(allAutonomous.length / ITEMS_PER_PAGE));
  const capPages = Math.max(1, Math.ceil(allCapability.length / ITEMS_PER_PAGE));

  const autoPage = autoPagination.signature === autoSignature ? autoPagination.page : 0;
  const capPage = capPagination.signature === capSignature ? capPagination.page : 0;
  const safeAutoPage = Math.min(autoPage, autoPages - 1);
  const safeCapPage = Math.min(capPage, capPages - 1);

  const autonomous = allAutonomous.slice(
    safeAutoPage * ITEMS_PER_PAGE,
    (safeAutoPage + 1) * ITEMS_PER_PAGE,
  );
  const capability = allCapability.slice(
    safeCapPage * ITEMS_PER_PAGE,
    (safeCapPage + 1) * ITEMS_PER_PAGE,
  );

  const nextAutoPage = () => setAutoPagination((current) => ({
    signature: autoSignature,
    page: ((current.signature === autoSignature ? current.page : 0) + 1) % autoPages,
  }));
  const nextCapPage = () => setCapPagination((current) => ({
    signature: capSignature,
    page: ((current.signature === capSignature ? current.page : 0) + 1) % capPages,
  }));

  const assigned = Math.round(stats.assigned_pct || 0);
  const autonomousPct = Math.round(stats.autonomous_pct || 0);
  const capabilityPct = Math.round(stats.capability_pct || 0);
  const totalHours = stats.quarter_work_hour || 0;
  // 差异 = 已排 - 至今预期（正数=超排，负数=少排）
  const expectedByToday = stats.expected_hours_by_today;
  const diffValue = expectedByToday != null ? Math.round((totalHours - expectedByToday) * 10) / 10 : null;
  const diffSign = diffValue === null ? null : diffValue > 0 ? '+' : '';
  const diffColor = diffValue === null ? ''
    : diffValue > 0 ? 'text-red-500'
    : diffValue < 0 ? 'text-amber-500'
    : 'text-emerald-600';
  // 解析 detail 为两部分：【任务分布情况分析】和【工时排布情况分析】
  const parseRiskDetail = (raw) => {
    if (!raw || typeof raw !== 'string') return { task: null, workHour: null };
    const taskIdx = raw.indexOf('【工时排布情况分析】');
    if (taskIdx === -1) return { task: raw.trim(), workHour: null };
    const taskPart = raw.substring(0, taskIdx).replace(/^【任务分布情况分析】\s*/u, '').trim();
    const workPart = raw.substring(taskIdx).replace(/^【工时排布情况分析】\s*/u, '').trim();
    return { task: taskPart, workHour: workPart };
  };
  const riskDetail = parseRiskDetail(risk.detail);
  const donutSegments = [
    { pct: assigned, color: '#d04934', label: '指派', offset: 0 },
    { pct: autonomousPct, color: '#10b981', label: '自主', offset: -assigned },
    { pct: capabilityPct, color: '#1b9aee', label: '能力', offset: -(assigned + autonomousPct) },
  ];

  return (
    <>
      <style>{`
        @keyframes drawCircle {
          from { stroke-dasharray: 0, 100; }
        }
        .chart-segment {
          animation: drawCircle 1s ease-out forwards;
        }
        .chart-segment:nth-child(2) { animation-delay: 0.15s; }
        .chart-segment:nth-child(3) { animation-delay: 0.3s; }
      `}</style>
      <div className="grid gap-3 xl:grid-cols-2">
      <ModulePanel title="需求雷达" tone="sky">
        {keywords.length > 0 ? (
          <div>
            <div className="flex flex-wrap gap-1.5">
              {keywords.map((kw, index) => {
                const tone = keywordTone(index);
                const active = activeKeywordIndex === index;
                return (
                  <button
                    key={kw.word}
                    type="button"
                    className={`group relative flex h-6 max-w-[128px] items-center gap-1.5 rounded-md border border-transparent px-2 text-left text-[12px] font-medium leading-4 transition ${
                      active ? `${tone.activeRow} border-slate-200` : `${tone.row} text-slate-600`
                    }`}
                    onClick={() => setExpandedKeyword(index)}
                  >
                    <span className={`absolute left-0 top-1.5 h-4 w-0.5 rounded-full transition-opacity ${tone.bar} ${active ? 'opacity-100' : 'opacity-0'}`} />
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot} ${index === 0 ? 'animate-pulse' : ''}`} />
                    <span className="truncate">{kw.word}</span>
                  </button>
                );
              })}
            </div>

            {selectedKeyword ? (
              <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                <div className="mb-2 flex items-center gap-2 pr-2">
                  <div className="min-w-0 flex-1 truncate text-[13px] font-bold leading-5 text-slate-800">{selectedKeyword.word}</div>
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${selectedTone.dot}`} />
                </div>
                <div className="space-y-2 text-[12px] leading-5 text-slate-600">
                  <div>
                    <span className="font-semibold text-slate-700">存量：</span>
                    {selectedKeyword.suggestions?.dig_deeper || '-'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-700">升维：</span>
                    {selectedKeyword.suggestions?.quality_up || '-'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-700">探索：</span>
                    {selectedKeyword.suggestions?.look_forward || '-'}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-200 px-3 py-8 text-center text-[12px] text-slate-400">
            暂无需求关键词
          </div>
        )}
      </ModulePanel>

      <ModulePanel
        title="自主型建议"
        tone="amber"
        actions={
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium text-slate-400 tabular-nums">{safeAutoPage + 1}/{autoPages}</span>
            <button
              type="button"
              className="flex h-5 w-5 items-center justify-center rounded text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              onClick={nextAutoPage}
              title="换一批"
              aria-label="换一批"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
              </svg>
            </button>
          </div>
        }
      >
        <div className="divide-y divide-slate-100">
          {autonomous.map((item, index) => (
            <div key={`${item.source_task}-${safeAutoPage * ITEMS_PER_PAGE + index}`} className="py-2 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold leading-5 text-slate-800">{item.task_template?.title || item.source_task}</div>
                  <div className="mt-0.5 text-[12px] leading-5 text-slate-500">{item.problem}</div>
                </div>
                <ApplyButton
                  disabled={applyingKeys.has(`autonomous-${safeAutoPage * ITEMS_PER_PAGE + index}`)}
                  onClick={() => handleApplySuggestion('autonomous', item, safeAutoPage * ITEMS_PER_PAGE + index)}
                />
              </div>
              <div className="mt-1 text-[12px] leading-4 text-amber-700">
                {(Array.isArray(item.task_template?.outputs) && item.task_template.outputs.length > 0)
                  ? `产出：${item.task_template.outputs.join('，')}`
                  : item.action || '-'}
              </div>
            </div>
          ))}
        </div>
      </ModulePanel>

      <ModulePanel title="任务分布与风险" tone="emerald">
        <div className="flex items-center gap-4">
          {/* 饼图 */}
          <div className="relative w-20 h-20 shrink-0">
            <svg viewBox="0 0 36 36" className="w-full h-full">
              <path className="text-slate-100" strokeWidth="3.5" stroke="currentColor" fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              {donutSegments.filter((s) => s.pct > 0).map((seg) => (
                <path key={seg.label}
                  className="chart-segment"
                  strokeWidth="3.5" stroke={seg.color} fill="none"
                  strokeDasharray={`${seg.pct}, 100`}
                  strokeDashoffset={seg.offset}
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
              ))}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-base font-bold text-slate-800 leading-none">{totalHours}</span>
              <span className="text-[10px] text-slate-400 font-medium mt-0.5">人天</span>
            </div>
          </div>

          {/* 图例 + 统计 */}
          <div className="flex-1 flex items-center">
            {/* 图例 */}
            <div className="space-y-1 text-[12px] leading-4">
              {donutSegments.map((seg) => (
                <div key={seg.label} className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: seg.color }} />
                  <span className="text-slate-500">{seg.label}</span>
                  <span className="font-semibold text-slate-800">{seg.pct}%</span>
                </div>
              ))}
            </div>
            {/* 分隔线 */}
            <div className="self-stretch w-px bg-slate-200 mx-3" />
            {/* 统计 */}
            <div className="space-y-1 text-[12px] leading-4">
              <div className="flex gap-1.5"><span className="text-slate-500">已排</span><span className="font-semibold">{stats.quarter_work_hour || '-'}d</span></div>
              <div className="flex gap-1.5"><span className="text-slate-500">完成</span><span className="font-semibold text-emerald-600">{stats.quarter_completed_work_hour || '-'}d</span></div>
              <div className="flex gap-1.5"><span className="text-slate-500">至今</span><span className="font-semibold">{stats.expected_hours_by_today || '-'}d</span></div>
              <div className="flex gap-1.5"><span className="text-slate-500">差异</span><span className={`font-semibold ${diffColor}`}>{diffValue !== null ? `${diffSign}${diffValue}d` : '-'}</span></div>
            </div>
          </div>
        </div>

        <div className="mt-2 border-t border-slate-100 pt-2 space-y-2">
          {riskDetail.task ? (
            <div className="text-[12px] leading-5 text-slate-600">
              <span className="font-semibold text-slate-700">任务分布 · </span>
              {riskDetail.task}
            </div>
          ) : null}
          {riskDetail.workHour ? (
            <div className="text-[12px] leading-5 text-slate-600">
              <span className="font-semibold text-slate-700">工时排布 · </span>
              {riskDetail.workHour}
            </div>
          ) : null}
          {!riskDetail.task && !riskDetail.workHour && (
            <div className="text-[12px] leading-5 text-slate-400">暂无分析结论</div>
          )}
        </div>
        {(risk.alerts || []).length > 0 ? (
          <div className="mt-1 flex flex-wrap gap-1">
            {risk.alerts.map((alert, index) => (
              <span key={index} className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${alert.level === 'red' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                {alert.description}
              </span>
            ))}
          </div>
        ) : null}
      </ModulePanel>

      <ModulePanel
        title="能力型建议"
        tone="violet"
        actions={
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium text-slate-400 tabular-nums">{safeCapPage + 1}/{capPages}</span>
            <button
              type="button"
              className="flex h-5 w-5 items-center justify-center rounded text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              onClick={nextCapPage}
              title="换一批"
              aria-label="换一批"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
              </svg>
            </button>
          </div>
        }
      >
        <div className="divide-y divide-slate-100">
          {capability.map((item, index) => (
            <div key={`${item.direction}-${safeCapPage * ITEMS_PER_PAGE + index}`} className="py-2 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold leading-5 text-slate-800">{item.task_template?.title || item.direction}</div>
                  <div className="mt-0.5 text-[12px] leading-5 text-slate-500">{item.reason}</div>
                </div>
                <ApplyButton
                  disabled={applyingKeys.has(`capability-${safeCapPage * ITEMS_PER_PAGE + index}`)}
                  onClick={() => handleApplySuggestion('capability', item, safeCapPage * ITEMS_PER_PAGE + index)}
                />
              </div>
              <div className="mt-1 text-[12px] leading-4 text-violet-700">
                <span>产出：{item.output_required || (Array.isArray(item.task_template?.outputs) ? item.task_template.outputs.join('，') : '') || '-'}</span>
                {item.effort_days ? <span className="ml-1">，预计 {item.effort_days}d</span> : null}
              </div>
            </div>
          ))}
        </div>
      </ModulePanel>
      </div>
    </>
  );
}
