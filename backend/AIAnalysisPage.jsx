// ── 绩效达标分析子组件 ────────────────────────────────────────

function TierGapPanel({ data }) {
  const gaps = data || {};
  const tiers = Array.isArray(gaps.tiers) ? gaps.tiers : [];
  const tierColors = {
    '1.5 (卓越)': 'border-l-purple-400',
    '1.2 (优秀)': 'border-l-emerald-400',
    '1.0 (良好)': 'border-l-sky-400',
    '0.8 (标准)': 'border-l-amber-400',
  };
  const tierBgs = {
    '1.5 (卓越)': 'bg-purple-50 text-purple-700',
    '1.2 (优秀)': 'bg-emerald-50 text-emerald-700',
    '1.0 (良好)': 'bg-sky-50 text-sky-700',
    '0.8 (标准)': 'bg-amber-50 text-amber-700',
  };
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <h3 className="mb-2 flex items-center gap-2 text-[13px] font-semibold leading-5 text-slate-800">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        达标差距
      </h3>
      {gaps.current_status ? (
        <div className="mb-2 rounded bg-slate-50 px-2 py-1.5 text-[12px] leading-5 text-slate-600">
          {gaps.current_status}
        </div>
      ) : null}
      {tiers.length > 0 ? (
        <div className="space-y-1.5">
          {tiers.map((t, i) => {
            const reachable = t.reachable !== false;
            return (
              <div key={i} className={`flex items-center justify-between rounded-md border-l-2 ${tierColors[t.tier] || 'border-l-slate-300'} bg-white px-3 py-1.5`}>
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${tierBgs[t.tier] || 'bg-slate-50 text-slate-600'}`}>{t.tier}</span>
                  <span className="text-[11px] text-slate-400">公司分 {t.company_score}</span>
                </div>
                <div className="flex items-center gap-3 text-right">
                  {t.gap_days > 0 ? (
                    <span className={`text-[12px] font-semibold ${reachable ? 'text-emerald-600' : 'text-red-500'}`}>
                      {reachable ? '还需' : '缺口'} {t.gap_days}d
                    </span>
                  ) : (
                    <span className="text-[12px] font-semibold text-emerald-600">✓ 已达标</span>
                  )}
                  <span className="text-[11px] text-slate-400">需 {t.hours_needed}d</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-[12px] text-slate-400">暂无差距分析</div>
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
