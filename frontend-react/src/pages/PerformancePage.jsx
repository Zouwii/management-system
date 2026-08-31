import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchPerformanceHistory, fetchOrganizationScopeOptions } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import { ROLES } from '../constants/roles';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { performanceArchives as fallbackArchives } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

const PERFORMANCE_THRESHOLD = 1.0;
const BAND_GUIDES = [
  { threshold: 2.0, label: '杰出', range: '>= 2.0' },
  { threshold: 1.5, label: '优秀', range: '1.5 - 2.0' },
  { threshold: 1.2, label: '超出期望', range: '1.2 - 1.5' },
  { threshold: 1.0, label: '符合期望', range: '1.0 - 1.2' },
  { threshold: 0.8, label: '需要提高', range: '0.8 - 1.0' },
  { threshold: 0.5, label: '需要改进', range: '0.5 - 0.8' },
  { threshold: 0.0, label: '不及格', range: '< 0.5' },
];

function getPerformanceBand(score) {
  if (score >= 2) {
    return '杰出';
  }

  if (score >= 1.5) {
    return '优秀';
  }

  if (score >= 1.2) {
    return '超出期望';
  }

  if (score >= 1) {
    return '符合期望';
  }

  if (score >= 0.8) {
    return '需要提高';
  }

  if (score >= 0.5) {
    return '需要改进';
  }

  return '不及格';
}

function getBandClass(score) {
  if (score >= 2) {
    return 'border-emerald-200 bg-emerald-100 text-emerald-800';
  }

  if (score >= 1.5) {
    return 'border-teal-100 bg-teal-50 text-teal-700';
  }

  if (score >= 1.2) {
    return 'border-emerald-100 bg-emerald-50 text-emerald-700';
  }

  if (score >= 1) {
    return 'border-sky-100 bg-sky-50 text-sky-700';
  }

  if (score >= 0.8) {
    return 'border-amber-100 bg-amber-50 text-amber-700';
  }

  if (score >= 0.5) {
    return 'border-orange-100 bg-orange-50 text-orange-700';
  }

  return 'border-rose-100 bg-rose-50 text-rose-700';
}

function getThresholdClass(score) {
  return score >= PERFORMANCE_THRESHOLD
    ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
    : 'border-rose-100 bg-rose-50 text-rose-700';
}

function formatDelta(delta) {
  const absoluteDelta = Math.abs(delta).toFixed(2);
  return `${delta >= 0 ? '较上季度上升' : '较上季度下降'} ${absoluteDelta}`;
}

function HelpLabel({ label, tip, highlighted = false }) {
  return (
    <span className={`relative inline-flex pr-3 ${highlighted ? 'font-semibold text-slate-900' : 'font-medium text-slate-500'}`}>
      <span>{label}</span>
      <span
        className="absolute -right-0.5 -top-1 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-slate-200 bg-white text-[9px] font-semibold text-slate-400"
        title={tip}
      >
        ?
      </span>
    </span>
  );
}

export default function PerformancePage() {
  const user = useAuthStore((state) => state.user);
  const canViewAllPeople = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const [searchParams] = useSearchParams();
  const targetFromQuery = searchParams.get('target') ?? '';
  const defaultTarget = canViewAllPeople
    ? (targetFromQuery || user?.name || fallbackArchives.李四.targetLabel)
    : (user?.name ?? fallbackArchives.李四.targetLabel);
  const [archive, setArchive] = useState(fallbackArchives[user?.name] ?? fallbackArchives.李四);
  const [memberOptions, setMemberOptions] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState(defaultTarget);
  const [selectedTeam, setSelectedTeam] = useState('');
  const [teams, setTeams] = useState([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [showMoreColumns, setShowMoreColumns] = useState(false);
  const initialLoadDone = useRef(false);

  // 加载小组列表
  useEffect(() => {
    if (!canViewAllPeople) return;
    fetchOrganizationScopeOptions('QUARTER_PERFORMANCE').then((res) => {
      const list = (res?.data?.teams || []).map((team) => ({
        key: team.key || ({ NAV: 'nav', INTEGRATION: 'servo' }[team.teamCode || team.code] || ''),
        label: team.label || team.teamName || team.name,
      })).filter((team) => team.key);
      setTeams(list);
      if (list.length && !selectedTeam) {
        setSelectedTeam(list[0].key);
      }
    }).catch(() => {});
  }, [canViewAllPeople, selectedTeam]);

  // 加载成员列表（按选中小组过滤）
  useEffect(() => {
    if (!canViewAllPeople || !selectedTeam) return;
    const teamCode = ({ nav: 'NAV', servo: 'INTEGRATION' })[selectedTeam] || selectedTeam;
    fetchOrganizationScopeOptions('QUARTER_PERFORMANCE', { teamCode }).then((res) => {
      const mapped = (res?.data?.members || [])
        .map((m) => ({
          id: m.userName || m.userId,
          name: m.userName || m.userId,
          team: m.teamName || m.teamLabel || '',
          userId: m.userId,
        }));
      setMemberOptions(mapped);
      if (mapped.length && !mapped.find((m) => m.id === selectedTarget)) {
        setSelectedTarget(mapped[0].id);
      }
    }).catch(() => {});
  }, [canViewAllPeople, selectedTarget, selectedTeam]);

  useEffect(() => {
    if (initialLoadDone.current) return;
    let active = true;

    fetchPerformanceHistory(user, { target: defaultTarget }).then((response) => {
      if (active && !initialLoadDone.current) {
        setArchive(response.data);
        // 仅在用户尚未手动选人时自动同步下拉框
        setSelectedTarget((prev) => {
          if (prev === defaultTarget || prev === '') {
            return response.data.targetLabel ?? defaultTarget;
          }
          return prev;
        });
        initialLoadDone.current = true;
      }
    });

    return () => {
      active = false;
    };
  }, [defaultTarget, user]);

  const history = archive.history ?? [];
  const currentQuarter = history[history.length - 1];
  const previousQuarter = history[history.length - 2];
  const displayHistory = [...history].reverse();
  const trendHistory = history;
  const quarterDeltaValue = currentQuarter && previousQuarter
    ? currentQuarter.finalScore - previousQuarter.finalScore
    : 0;
  const quarterDelta = quarterDeltaValue.toFixed(2);
  const trendMaxScore = Math.max(...trendHistory.map((item) => item.finalScore), 2);
  const trendMinScore = Math.min(...trendHistory.map((item) => item.finalScore), 0);
  const chartHeight = 320;
  const chartPadding = 32;
  const availableHeight = chartHeight - chartPadding * 2;
  const thresholdLines = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0].filter((value) => value >= trendMinScore && value <= trendMaxScore);
  const chartWidth = 720;
  const xPadding = 88;
  const usableChartWidth = chartWidth - xPadding * 2;
  const pointGap = trendHistory.length > 1 ? usableChartWidth / (trendHistory.length - 1) : 0;
  const trendPoints = trendHistory.map((item, index) => {
    const x = trendHistory.length > 1 ? xPadding + index * pointGap : chartWidth / 2;
    const y = chartPadding + (trendMaxScore - item.finalScore) / Math.max(trendMaxScore - trendMinScore, 0.4) * availableHeight;

    return {
      ...item,
      x,
      y,
    };
  });
  const linePath = trendPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x},${point.y}`)
    .join(' ');
  const currentBandIndex = currentQuarter
    ? BAND_GUIDES.findIndex((item) => item.label === getPerformanceBand(currentQuarter.finalScore))
    : -1;
  const nextBand = currentBandIndex > 0 ? BAND_GUIDES[currentBandIndex - 1] : null;
  const projectedNeed = nextBand && currentQuarter
    ? Math.max(nextBand.threshold - (currentQuarter.carryScore ?? 0), 0)
    : 0;

  async function handleQuery() {
    setIsQuerying(true);

    try {
      const response = await fetchPerformanceHistory(user, {
        target: selectedTarget,
      });
      setArchive(response.data);
      // 仅更新选中状态，不触发 URL 变动（避免重复请求）
      const nextTarget = response.data.targetLabel ?? selectedTarget;
      setSelectedTarget(nextTarget);
    } finally {
      setIsQuerying(false);
    }
  }

  return (
    <EmployeeLayout>
      <SectionTitle
        title="绩效管理"
      />

      {canViewAllPeople ? (
        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="text-lg font-semibold text-slate-900">绩效查询</div>
            <div className="flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto">
              <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                <span className="shrink-0">小组</span>
                <select
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-slate-400 sm:w-[160px] sm:flex-none"
                  value={selectedTeam}
                  onChange={(e) => setSelectedTeam(e.target.value)}
                >
                  {teams.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>
              </label>
              <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                <span className="shrink-0">人员</span>
                <select
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-slate-400 sm:w-[200px] sm:flex-none"
                  value={selectedTarget}
                  onChange={(event) => setSelectedTarget(event.target.value)}
                >
                  {memberOptions.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleQuery}
                disabled={isQuerying}
              >
                {isQuerying ? '查询中...' : '查询绩效'}
              </button>
            </div>
          </div>
        </Card>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(0,0.9fr)]">
        <Card className={`p-6 ${getThresholdClass(currentQuarter?.finalScore ?? 0)}`}>
          <div className="text-sm">当前季度最终绩效</div>
          <div className="mt-3 flex items-end justify-between gap-4">
            <div>
              <div className="text-4xl font-semibold">{currentQuarter ? currentQuarter.finalScore.toFixed(2) : '-'}</div>
              <div className="mt-2 text-sm">
                {currentQuarter ? `${currentQuarter.quarter} · ${getPerformanceBand(currentQuarter.finalScore)}` : '暂无归档'}
              </div>
            </div>
            {currentQuarter ? (
              <span className={`inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${getBandClass(currentQuarter.finalScore)}`}>
                {getPerformanceBand(currentQuarter.finalScore)}
              </span>
            ) : null}
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-sm">本季度结余</div>
          <div className="mt-3 text-4xl font-semibold text-slate-900">{currentQuarter ? (currentQuarter.carryScore ?? 0).toFixed(3) : '-'}</div>
          <div className="mt-3 text-sm">
            {currentQuarter ? `${currentQuarter.quarter} 本季度结余` : '暂无归档'}
          </div>
        </Card>

        <Card className={`p-6 ${Number(quarterDelta) >= 0 ? 'border-emerald-100 bg-emerald-50 text-emerald-700' : 'border-rose-100 bg-rose-50 text-rose-700'}`}>
          <div className="text-sm">本季变化</div>
          <div className="mt-3 text-4xl font-semibold">
            {Number(quarterDelta) >= 0 ? '+' : ''}
            {quarterDelta}
          </div>
          <div className="mt-4 text-sm">
            {previousQuarter ? `${formatDelta(quarterDeltaValue)}，对比季度为 ${previousQuarter.quarter}` : '暂无可对比上季度数据'}
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="p-6">
          <div className="text-lg font-semibold text-slate-900">下季度档位预估</div>
          <div className="mt-1 text-sm text-slate-500">结合本季度结余，直接看下季度要达到更高档位还差多少基础绩效。</div>
          {currentQuarter ? (
            <div className="mt-5 space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                <div className="text-sm text-slate-500">当前档位</div>
                <div className="mt-2 flex items-center justify-between gap-4">
                  <div className="text-2xl font-semibold text-slate-900">{getPerformanceBand(currentQuarter.finalScore)}</div>
                  <span className={`inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${getBandClass(currentQuarter.finalScore)}`}>
                    最终绩效 {currentQuarter.finalScore.toFixed(2)}
                  </span>
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                {nextBand ? (
                  <>
                    <div className="text-sm text-slate-500">若想进入下一档</div>
                    <div className="mt-2 text-xl font-semibold text-slate-900">{nextBand.label}</div>
                    <div className="mt-2 text-sm text-slate-600">
                      下季度基础绩效至少需要
                      {' '}
                      <span className="font-semibold text-slate-900">{projectedNeed.toFixed(3)}</span>
                      ，叠加当前结余后才有机会达到
                      {' '}
                      <span className="font-semibold text-slate-900">{nextBand.threshold.toFixed(1)}</span>
                      {' '}
                      档位门槛。
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-slate-600">当前已经位于最高档位，无需再做跨档预估。</div>
                )}
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                参考口径：低于 0.8 不产生新结余，已有结余按“先用再衰减”处理。
              </div>
            </div>
          ) : null}
        </Card>

        <Card className="p-6">
          <div className="text-lg font-semibold text-slate-900">评分标准</div>
          <div className="mt-1 text-sm text-slate-500">3.1.2 档位标准按最终绩效直接映射，查看分数对应的正式档位。</div>
          <div className="mt-5 grid gap-2">
            {BAND_GUIDES.map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${getBandClass(item.threshold)}`}>
                  {item.label}
                </span>
                <div className="text-sm font-medium text-slate-600">{item.range}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">季度绩效记录</div>
              <div className="mt-1 text-sm text-slate-500">按最近季度优先展示，默认只看核心结果，点开后可查看绩效构成明细。</div>
            </div>
            <button
              type="button"
              className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
              onClick={() => setShowMoreColumns((value) => !value)}
            >
              {showMoreColumns ? '收起明细' : '展开更多'}
            </button>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">季度</th>
                <th className="px-5 py-4 text-left">
                  <HelpLabel label="最终绩效" tip="用于确定正式档位的最终分数，是本季度最核心的绩效结果。" highlighted />
                </th>
                <th className="px-5 py-4 text-left">
                  <HelpLabel label="档位" tip="根据最终绩效映射得到的正式绩效档位，如杰出、优秀、超出期望等。" />
                </th>
                <th className="px-5 py-4 text-left">
                  <HelpLabel label="本季度结余" tip="升档：上季度结余+补偿值-上季度衰减；不升档：上季度结余×0.75+本季度溢出值" highlighted />
                </th>
                <th className="px-5 py-4 text-left">
                  <HelpLabel label="结余绩效" tip="结余绩效=本季度绩效+上季度结余" />
                </th>
                {showMoreColumns ? (
                  <>
                    <th className="px-5 py-4 text-left">
                      <HelpLabel label="总体绩效" tip="工时绩效与主管绩效加权后的基础结果，尚未叠加结余影响。" />
                    </th>
                    <th className="px-5 py-4 text-left">
                      <HelpLabel label="工时绩效" tip="按季度工时完成与贡献情况计算得到的绩效分数。" />
                    </th>
                    <th className="px-5 py-4 text-left">
                      <HelpLabel label="主管绩效" tip="主管根据季度表现评定的绩效分数。" />
                    </th>
                  </>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {displayHistory.map((item, index) => (
                <tr key={item.quarter} className={index !== displayHistory.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-5 py-4 font-medium text-slate-900">{item.quarter}</td>
                  <td className={`px-5 py-4 font-medium ${(item.finalScore) >= PERFORMANCE_THRESHOLD ? 'text-emerald-700' : 'text-rose-700'}`}>{item.finalScore.toFixed(2)}</td>
                  <td className="px-5 py-4">
                    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${getBandClass(item.finalScore)}`}>
                      {getPerformanceBand(item.finalScore)}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-medium text-slate-900">{(item.carryScore ?? 0).toFixed(3)}</td>
                  <td className="px-5 py-4 font-medium text-slate-900">{(item.balanceScore ?? 0).toFixed(3)}</td>
                  {showMoreColumns ? (
                    <>
                      <td className="px-5 py-4 text-slate-600">{item.overallScore.toFixed(3)}</td>
                      <td className="px-5 py-4 text-slate-600">{item.hourScore.toFixed(2)}</td>
                      <td className="px-5 py-4 text-slate-600">{item.managerScore.toFixed(2)}</td>
                    </>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">绩效变化趋势</div>
            <div className="mt-1 text-sm text-slate-500">只看最终绩效的季度变化，并对照完整档位边界判断当前处在哪个区间。</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">阈值线：0.5 / 0.8 / 1.0 / 1.2 / 1.5 / 2.0</div>
        </div>
        <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-6">
          <div className="overflow-x-auto">
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="block h-[380px] w-full min-w-[960px] overflow-visible">
              {thresholdLines.map((line) => {
                const y = chartPadding + (trendMaxScore - line) / Math.max(trendMaxScore - trendMinScore, 0.4) * availableHeight;
                const bandLabel = BAND_GUIDES.find((item) => item.threshold === line)?.label;
                return (
                  <g key={line}>
                    <line x1={xPadding} y1={y} x2={chartWidth - xPadding} y2={y} stroke="#cbd5e1" strokeDasharray="3 3" strokeWidth="1" />
                    {bandLabel ? (
                      <text x={xPadding - 18} y={y + 2} textAnchor="end" fontSize="12" fill="#94a3b8">{bandLabel}</text>
                    ) : null}
                    <text x={chartWidth - xPadding + 18} y={y + 2} textAnchor="start" fontSize="12" fill="#64748b">{line.toFixed(1)}</text>
                  </g>
                );
              })}
              <path d={linePath} fill="none" stroke="#0f172a" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
              {trendPoints.map((point, index) => (
                <g key={point.quarter}>
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={index === trendPoints.length - 1 ? 8 : 6}
                    fill={point.finalScore >= PERFORMANCE_THRESHOLD ? '#059669' : '#e11d48'}
                  />
                  <rect
                    x={point.x - 20}
                    y={point.y - 34}
                    width="40"
                    height="18"
                    rx="9"
                    fill="rgba(255,255,255,0.92)"
                  />
                  <text x={point.x} y={point.y - 22} textAnchor="middle" fontSize="12" fill="#0f172a">{point.finalScore.toFixed(2)}</text>
                  <text x={point.x} y={chartHeight - 16} textAnchor="middle" fontSize="12" fill="#475569">{point.quarter}</text>
                </g>
              ))}
            </svg>
          </div>
        </div>
      </Card>


    </EmployeeLayout>
  );
}
