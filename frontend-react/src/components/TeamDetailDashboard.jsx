import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Card from './Card';
import SectionTitle from './SectionTitle';
import ManagerLayout from '../layouts/ManagerLayout';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { formatDateTime } from '../utils/workHours';
import { fetchOrganizationScopeOptions, fetchTeamPerformance } from '../api/dashboard';

const PERFORMANCE_LINE_COLORS = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#ea580c',
  '#4f46e5',
  '#0f766e',
  '#9333ea',
];

function TeamPerformanceTrendChart({ data, members }) {
  const width = 960;
  const height = 400;
  const padding = { top: 24, right: 28, bottom: 46, left: 52 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const yMax = 2.1;
  const yTicks = [0, 0.5, 0.8, 1, 1.2, 1.5, 2];
  const getX = (index) => (
    data.length > 1
      ? padding.left + (index * chartWidth) / (data.length - 1)
      : padding.left + chartWidth / 2
  );
  const getY = (score) => padding.top + ((yMax - score) / yMax) * chartHeight;

  return (
    <div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="block h-[400px] w-full min-w-[760px]"
          role="img"
          aria-label="团队成员季度绩效变化趋势图"
        >
          {yTicks.map((tick) => {
            const y = getY(tick);
            return (
              <g key={tick}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke={tick === 1 ? '#16a34a' : '#e2e8f0'}
                  strokeDasharray={tick === 1 ? '6 4' : '3 3'}
                />
                <text x={padding.left - 12} y={y + 4} textAnchor="end" fontSize="12" fill="#64748b">
                  {tick.toFixed(1)}
                </text>
              </g>
            );
          })}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={height - padding.bottom}
            stroke="#cbd5e1"
          />
          <line
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
            stroke="#cbd5e1"
          />
          {data.map((point, index) => (
            <text
              key={point.quarter}
              x={getX(index)}
              y={height - 18}
              textAnchor="middle"
              fontSize="12"
              fill="#64748b"
            >
              {point.quarter}
            </text>
          ))}
          {members.map((member, memberIndex) => {
            const color = PERFORMANCE_LINE_COLORS[memberIndex % PERFORMANCE_LINE_COLORS.length];
            const path = data.map((point, index) => {
              const score = Number(point[member]);
              if (!Number.isFinite(score)) return null;
              return { x: getX(index), y: getY(score), score, quarter: point.quarter };
            });
            let hasPreviousPoint = false;
            const pathData = path.map((point) => {
              if (!point) {
                hasPreviousPoint = false;
                return '';
              }
              const command = hasPreviousPoint ? 'L' : 'M';
              hasPreviousPoint = true;
              return `${command} ${point.x} ${point.y}`;
            }).join(' ');

            return (
              <g key={member}>
                <path d={pathData} fill="none" stroke={color} strokeWidth="2.5" />
                {path.filter(Boolean).map((point) => (
                  <circle
                    key={`${member}-${point.quarter}`}
                    cx={point.x}
                    cy={point.y}
                    r="4"
                    fill="#fff"
                    stroke={color}
                    strokeWidth="2.5"
                  >
                    <title>{`${member} · ${point.quarter} · ${point.score.toFixed(2)}`}</title>
                  </circle>
                ))}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-2">
        {members.map((member, index) => (
          <div key={member} className="flex items-center gap-2 text-xs text-slate-600">
            <span
              className="h-0.5 w-5 rounded-full"
              style={{ backgroundColor: PERFORMANCE_LINE_COLORS[index % PERFORMANCE_LINE_COLORS.length] }}
            />
            <span>{member}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatRawDays(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toFixed(1) : '0.0';
}

function getRiskLevel(actual, expected) {
  const ratio = expected > 0 ? actual / expected : 1;

  if (ratio < 0.5) {
    return '高风险';
  }

  if (ratio < 0.8) {
    return '中风险';
  }

  if (ratio < 1.0) {
    return '低风险';
  }

  return '充足';
}

function getRiskTagClass(level) {
  if (level === '高风险') {
    return 'bg-rose-50 text-rose-700';
  }

  if (level === '中风险') {
    return 'bg-amber-50 text-amber-700';
  }

  if (level === '低风险') {
    return 'bg-sky-50 text-sky-700';
  }

  return 'bg-emerald-50 text-emerald-700';
}

function getRiskRowClass(level) {
  if (level === '高风险') {
    return 'bg-rose-50/60';
  }

  if (level === '中风险') {
    return 'bg-amber-50/60';
  }

  return '';
}

function RiskExplanation({ metric }) {
  return (
    <span className="block space-y-1 whitespace-nowrap text-left">
      <span className="mb-1.5 block border-b border-slate-600 pb-1.5 text-slate-200">{metric}</span>
      <span className="block"><span className="font-semibold text-rose-300">高风险：</span>&lt; 50%</span>
      <span className="block"><span className="font-semibold text-amber-300">中风险：</span>≥ 50% 且 &lt; 80%</span>
      <span className="block"><span className="font-semibold text-sky-300">低风险：</span>≥ 80% 且 &lt; 100%</span>
      <span className="block"><span className="font-semibold text-emerald-300">充足：</span>≥ 100%</span>
    </span>
  );
}

function normalizeHoursRows(rows) {
  return rows.map((row) => {
    const quarterExpectedHours = Number(row.quarterExpectedHours || 0);
    const currentExpectedHours = Number(row.currentExpectedHours || row.quarterExpectedHours || 0);
    const scheduledHours = Number(row.scheduledHours || 0);
    const completedHours = Number(row.completedHours || 0);
    const overdueEffectiveHours = Number(row.overdueEffectiveHours || 0);
    const overdueCompletedHours = Number(row.overdueCompletedHours || 0);
    const allocationActualHours = scheduledHours + overdueEffectiveHours;
    const completionActualHours = completedHours + overdueCompletedHours;
    const allocationDelta = Number.isFinite(Number(row.allocationDelta))
      ? Number(row.allocationDelta)
      : (scheduledHours + overdueEffectiveHours - quarterExpectedHours);
    const completionDelta = Number.isFinite(Number(row.completionDelta))
      ? Number(row.completionDelta)
      : (completedHours + overdueCompletedHours - quarterExpectedHours);
    return {
      ...row,
      quarterExpectedHours,
      currentExpectedHours,
      scheduledHours,
      completedHours,
      overdueEffectiveHours,
      overdueCompletedHours,
      allocationActualHours,
      completionActualHours,
      allocationDelta,
      completionDelta,
      allocationInsufficient: allocationDelta < 0,
      completionInsufficient: completionDelta < 0,
      allocationRiskLevel: getRiskLevel(allocationActualHours, quarterExpectedHours),
      completionRiskLevel: getRiskLevel(completionActualHours, quarterExpectedHours),
    };
  });
}

function generateQuarterOptions() {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentQuarter = Math.floor(now.getMonth() / 3) + 1;
  const quarters = [];
  // 从 2025Q1 生成到当前季度
  for (let y = 2025; y <= currentYear; y++) {
    const endQ = y === currentYear ? currentQuarter : 4;
    for (let q = 1; q <= endQ; q++) {
      quarters.push(`${y}Q${q}`);
    }
  }
  // 最新季度排前面
  return quarters.reverse();
}

function getDefaultQuarter() {
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  const defaultQ = q === 1 ? 4 : q - 1;
  const defaultY = q === 1 ? now.getFullYear() - 1 : now.getFullYear();
  return `${defaultY}Q${defaultQ}`;
}

function parseQuarterLabel(label) {
  const match = String(label || '').match(/^(\d{4})Q([1-4])$/);
  if (!match) return null;
  return { year: Number(match[1]), quarter: Number(match[2]) };
}

function buildExpectedDateRange(view) {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  const format = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;

  if (view === 'last_quarter') {
    const lastQuarterStartMonth = quarterStartMonth === 0 ? 9 : quarterStartMonth - 3;
    const lastQuarterYear = quarterStartMonth === 0 ? now.getFullYear() - 1 : now.getFullYear();
    return {
      startDate: format(new Date(lastQuarterYear, lastQuarterStartMonth, 1, 0, 0, 0)),
      endDate: format(new Date(lastQuarterYear, lastQuarterStartMonth + 3, 0, 23, 59, 59)),
    };
  }

  if (view === 'current') {
    return {
      startDate: format(new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0)),
      endDate: format(new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59)),
    };
  }

  return {
    startDate: format(new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0)),
    endDate: format(new Date(now.getFullYear(), quarterStartMonth + 3, 0, 23, 59, 59)),
  };
}

export default function TeamDetailDashboard({
  title,
  desc,
  teamCode,
  fetcher,
  fallbackRows,
  organizationScopeCode = 'DEPARTMENT_EFFECTIVE_HOURS',
  showPerformance = true,
}) {
  const user = useAuthStore((state) => state.user);
  const [searchParams] = useSearchParams();
  const initialExpectedParam = searchParams.get('expected');
  const initialExpectedView = ['quarter', 'current', 'last_quarter'].includes(initialExpectedParam)
    ? initialExpectedParam
    : 'current';
  const initialHoursAbnormal = ({
    abnormal: '只看异常成员',
    allocation: '只看分配不足',
    completion: '只看完成不足',
  })[searchParams.get('hoursAbnormal') || ''] ?? '全部成员';
  const [rows, setRows] = useState(fallbackRows);
  const [memberOptions, setMemberOptions] = useState(['全部', ...fallbackRows.map((row) => row.name)]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [hoursMemberFilter, setHoursMemberFilter] = useState('全部');
  const [hoursAbnormalFilter, setHoursAbnormalFilter] = useState(initialHoursAbnormal);
  const [allocationSort, setAllocationSort] = useState('none');
  const [completionSort, setCompletionSort] = useState('none');
  const [expectedView, setExpectedView] = useState(initialExpectedView);
  const [dateRange, setDateRange] = useState(() => buildExpectedDateRange(initialExpectedView));

  const [performanceMemberFilter, setPerformanceMemberFilter] = useState('全部');
  const performanceQuarters = useMemo(() => generateQuarterOptions(), []);
  const defaultQuarter = useMemo(() => getDefaultQuarter(), []);
  const [performanceQueryVersion, setPerformanceQueryVersion] = useState(0);
  const [performanceTrendData, setPerformanceTrendData] = useState([]);
  const [perfLoading, setPerfLoading] = useState(showPerformance);

  // 默认拉取最新绩效季度及之前最多 8 个季度，用于团队趋势图。
  useEffect(() => {
    let active = true;
    const appliedIndex = performanceQuarters.indexOf(defaultQuarter);
    const trendQuarters = performanceQuarters
      .slice(appliedIndex >= 0 ? appliedIndex : 0, (appliedIndex >= 0 ? appliedIndex : 0) + 8)
      .reverse();

    if (!showPerformance || !teamCode || trendQuarters.length === 0) {
      return undefined;
    }

    Promise.all(trendQuarters.map(async (quarterLabel) => {
      const parsed = parseQuarterLabel(quarterLabel);
      if (!parsed) return { quarter: quarterLabel, results: [] };

      try {
        const response = await fetchTeamPerformance(user, {
          year: parsed.year,
          quarter: parsed.quarter,
          teamCode,
        });
        return {
          quarter: quarterLabel,
          results: response?.data?.results ?? [],
        };
      } catch {
        return { quarter: quarterLabel, results: [] };
      }
    })).then((quarterResults) => {
      if (!active) return;
      setPerformanceTrendData(quarterResults);
      setPerfLoading(false);
    });

    return () => { active = false; };
  }, [defaultQuarter, performanceQuarters, performanceQueryVersion, showPerformance, teamCode, user]);

  function handlePerformanceQuery() {
    setPerfLoading(true);
    setPerformanceQueryVersion((version) => version + 1);
  }

  // 工时数据加载
  useEffect(() => {
    let active = true;

    fetcher(user, { expected: expectedView, ...dateRange }).then((response) => {
      if (!active) {
        return;
      }

      const nextRows = response.data.rows ?? fallbackRows;
      setRows(nextRows);
      setLastUpdatedAt(String(response?.data?.lastUpdatedAt || ''));
    });

    // 下拉成员列表：统一从组织 Scope 获取，排除管理员
    if (teamCode) {
      fetchOrganizationScopeOptions(organizationScopeCode, { teamCode }).then((res) => {
        if (!active) return;
        const names = (res?.data?.members || [])
          .map((m) => m.userName || m.userId)
          .filter(Boolean);
        setMemberOptions(names.length ? ['全部', ...names] : ['全部']);
      }).catch(() => {});
    }

    return () => {
      active = false;
    };
  }, [dateRange, expectedView, fallbackRows, fetcher, organizationScopeCode, teamCode, user]);

  useEffect(() => {
    const expectedParam = searchParams.get('expected');
    const nextExpectedView = ['quarter', 'current', 'last_quarter'].includes(expectedParam)
      ? expectedParam
      : 'current';
    const nextHoursAbnormal = ({
      abnormal: '只看异常成员',
      allocation: '只看分配不足',
      completion: '只看完成不足',
    })[searchParams.get('hoursAbnormal') || ''] ?? '全部成员';
    // URL 查询参数是外部状态，需要在路由变化后同步到筛选控件。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpectedView(nextExpectedView);
    setDateRange(buildExpectedDateRange(nextExpectedView));
    setHoursAbnormalFilter(nextHoursAbnormal);
  }, [searchParams]);

  function applyExpectedView(view) {
    setExpectedView(view);
    setDateRange(buildExpectedDateRange(view));
  }

  function handleDateRangeChange(field, value) {
    setExpectedView('custom');
    setDateRange((current) => {
      const next = { ...current, [field]: value };
      if (next.startDate && next.endDate && next.endDate < next.startDate) {
        if (field === 'startDate') next.endDate = next.startDate;
        else next.startDate = next.endDate;
      }
      return next;
    });
  }

  useEffect(() => {
    if (memberOptions.includes(hoursMemberFilter)) return;
    // 成员列表来自异步接口，切组后需要回退到有效选项。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHoursMemberFilter('全部');
  }, [hoursMemberFilter, memberOptions]);

  useEffect(() => {
    if (memberOptions.includes(performanceMemberFilter)) return;
    // 成员列表来自异步接口，切组后需要回退到有效选项。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPerformanceMemberFilter('全部');
  }, [memberOptions, performanceMemberFilter]);

  const allHourRows = useMemo(() => {
    const normalized = normalizeHoursRows(rows);
    return normalized.map((row) => ({
      ...row,
      selectedExpectedHours: row.quarterExpectedHours,
      allocationInsufficient: row.allocationDelta < 0,
      completionInsufficient: row.completionDelta < 0,
      allocationRiskLevel: getRiskLevel(
        row.scheduledHours + row.overdueEffectiveHours,
        row.quarterExpectedHours,
      ),
      completionRiskLevel: getRiskLevel(
        row.completedHours + row.overdueCompletedHours,
        row.quarterExpectedHours,
      ),
    }));
  }, [rows]);
  const visibleHourRows = useMemo(() => {
    const filteredRows = allHourRows.filter((row) => {
      if (hoursMemberFilter !== '全部' && row.name !== hoursMemberFilter) {
        return false;
      }

      if (hoursAbnormalFilter === '只看分配不足' && row.allocationDelta >= 0) {
        return false;
      }

      if (hoursAbnormalFilter === '只看完成不足' && row.completionDelta >= 0) {
        return false;
      }

      if (hoursAbnormalFilter === '只看异常成员' && row.allocationDelta >= 0 && row.completionDelta >= 0) {
        return false;
      }

      return true;
    });

    filteredRows.sort((left, right) => {
      if (allocationSort !== 'none') {
        return allocationSort === 'asc'
          ? left.allocationDelta - right.allocationDelta
          : right.allocationDelta - left.allocationDelta;
      }

      if (completionSort !== 'none') {
        return completionSort === 'asc'
          ? left.completionDelta - right.completionDelta
          : right.completionDelta - left.completionDelta;
      }

      return 0;
    });

    return filteredRows;
  }, [allHourRows, allocationSort, completionSort, hoursAbnormalFilter, hoursMemberFilter]);

  const performanceTrendChart = useMemo(() => {
    const rowNameMap = new Map();
    rows.forEach((row) => {
      const userId = String(row.userId || '');
      if (userId) rowNameMap.set(userId, row.name || row.userName || userId);
    });

    const resolveMemberName = (result) => (
      rowNameMap.get(String(result.userId || ''))
      || result.userName
      || result.userId
    );
    const memberNames = [];
    const memberNameSet = new Set();

    performanceTrendData.forEach(({ results }) => {
      results.forEach((result) => {
        const name = resolveMemberName(result);
        if (name && !memberNameSet.has(name)) {
          memberNameSet.add(name);
          memberNames.push(name);
        }
      });
    });

    const visibleMembers = performanceMemberFilter === '全部'
      ? memberNames
      : memberNames.filter((name) => name === performanceMemberFilter);
    const visibleMemberSet = new Set(visibleMembers);
    const data = performanceTrendData.map(({ quarter, results }) => {
      const point = { quarter };
      results.forEach((result) => {
        const name = resolveMemberName(result);
        const score = Number(result.finalScore);
        if (visibleMemberSet.has(name) && Number.isFinite(score)) {
          point[name] = score;
        }
      });
      return point;
    });

    return { data, members: visibleMembers };
  }, [performanceMemberFilter, performanceTrendData, rows]);

  const teamHoursSummary = useMemo(() => ({
    quarterExpectedHours: visibleHourRows.reduce((sum, row) => sum + row.quarterExpectedHours, 0),
    currentExpectedHours: visibleHourRows.reduce((sum, row) => sum + row.currentExpectedHours, 0),
    selectedExpectedHours: visibleHourRows.reduce((sum, row) => sum + row.selectedExpectedHours, 0),
    scheduledHours: visibleHourRows.reduce((sum, row) => sum + row.scheduledHours, 0),
    completedHours: visibleHourRows.reduce((sum, row) => sum + row.completedHours, 0),
    overdueEffectiveHours: visibleHourRows.reduce((sum, row) => sum + row.overdueEffectiveHours, 0),
    overdueCompletedHours: visibleHourRows.reduce((sum, row) => sum + row.overdueCompletedHours, 0),
    allocationDelta: visibleHourRows.reduce((sum, row) => sum + row.allocationDelta, 0),
    completionDelta: visibleHourRows.reduce((sum, row) => sum + row.completionDelta, 0),
  }), [visibleHourRows]);
  const teamHoursStats = useMemo(() => ({
    memberCount: visibleHourRows.length,
    allocationRiskCount: visibleHourRows.filter((row) => row.allocationDelta < 0).length,
    completionRiskCount: visibleHourRows.filter((row) => row.completionDelta < 0).length,
    highRiskCount: visibleHourRows.filter((row) => row.allocationRiskLevel === '高风险' || row.completionRiskLevel === '高风险').length,
  }), [visibleHourRows]);
  const currentIntervalWorkdayCount = useMemo(() => {
    const first = rows.find((r) => Number.isFinite(Number(r?.workdayCount)));
    return Number(first?.workdayCount || 0);
  }, [rows]);
  const expectedConfig = expectedView === 'custom'
    ? {
        label: '筛选区间预期有效工时',
        description: '当前筛选时间范围内的预期有效工时',
        summaryValue: teamHoursSummary.selectedExpectedHours,
        rowValue: 'selectedExpectedHours',
      }
    : expectedView === 'current'
    ? {
        label: '本季度至今天预期有效工时',
        description: '当前筛选成员本季度截至今天的预期有效工时',
        summaryValue: teamHoursSummary.selectedExpectedHours,
        rowValue: 'selectedExpectedHours',
      }
    : expectedView === 'last_quarter'
      ? {
          label: '上季度预期有效工时',
          description: '当前筛选成员上一季度的预期总有效工时',
          summaryValue: teamHoursSummary.selectedExpectedHours,
          rowValue: 'selectedExpectedHours',
        }
    : {
        label: '本季度预期有效工时',
        description: '当前筛选成员本季度的预期总有效工时',
        summaryValue: teamHoursSummary.selectedExpectedHours,
        rowValue: 'selectedExpectedHours',
      };

  return (
    <ManagerLayout>
      <SectionTitle
        title={title}
        desc={desc}
        right={(
          <div className="flex flex-wrap justify-end gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">最后同步：{formatDateTime(lastUpdatedAt)}</div>
          </div>
        )}
      />

      {showPerformance ? <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">工时情况</div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-4">
          {/* 第一行：时间区间 */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center">
              <div className="flex w-full flex-wrap items-center gap-3">
                <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                  <span className="shrink-0">开始时间</span>
                  <input type="datetime-local" step="1" value={dateRange.startDate}
                    onChange={(event) => handleDateRangeChange('startDate', event.target.value)}
                    max={dateRange.endDate || undefined}
                    className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none" />
                </label>
                <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                  <span className="shrink-0">结束时间</span>
                  <input type="datetime-local" step="1" value={dateRange.endDate}
                    onChange={(event) => handleDateRangeChange('endDate', event.target.value)}
                    min={dateRange.startDate || undefined}
                    className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none" />
                </label>
                <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={() => applyExpectedView('last_quarter')}
                  className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium ${expectedView === 'last_quarter' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'}`}>
                  上季度</button>
                <button type="button" onClick={() => applyExpectedView('quarter')}
                  className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium ${expectedView === 'quarter' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'}`}>
                  本季度</button>
                <button type="button" onClick={() => applyExpectedView('current')}
                  className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium ${expectedView === 'current' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'}`}>
                  本季度至今天</button>
                </div>
              </div>
            </div>
          </div>
          {/* 第二行：成员 + 排序 + 工作日 */}
          <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="whitespace-nowrap text-sm text-slate-500">成员</span>
                <select
                  value={hoursMemberFilter}
                  onChange={(event) => setHoursMemberFilter(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none"
                >
                  {memberOptions.map((member) => (
                    <option key={member} value={member}>{member === '全部' ? '全部成员' : member}</option>
                  ))}
                </select>
              </div>
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="whitespace-nowrap text-sm text-slate-500">分配差值排序</span>
                <select
                  value={allocationSort}
                  onChange={(event) => {
                    setAllocationSort(event.target.value);
                    if (event.target.value !== 'none') {
                      setCompletionSort('none');
                    }
                  }}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none"
                >
                  <option value="none">默认</option>
                  <option value="asc">升序</option>
                  <option value="desc">降序</option>
                </select>
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="whitespace-nowrap text-sm text-slate-500">完成差值排序</span>
                <select
                  value={completionSort}
                  onChange={(event) => {
                    setCompletionSort(event.target.value);
                    if (event.target.value !== 'none') {
                      setAllocationSort('none');
                    }
                  }}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none"
                >
                  <option value="none">默认</option>
                  <option value="asc">升序</option>
                  <option value="desc">降序</option>
                </select>
            </div>
            <div className="inline-flex w-fit items-center justify-self-end rounded-2xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-500">
              当前区间共 <span className="mx-1 font-medium text-slate-700">{formatRawDays(currentIntervalWorkdayCount)}</span> 个工作日
            </div>
          </div>
        </div>
        <div className="grid gap-5 border-b border-slate-200 bg-slate-50 px-5 py-5 md:grid-cols-2 xl:grid-cols-4">
          <Card className="p-5">
            <div className="text-sm text-slate-500">当前成员数</div>
            <div className="mt-2 text-3xl font-semibold text-slate-900">{teamHoursStats.memberCount}</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">{expectedConfig.label}</div>
            <div className="mt-2 text-3xl font-semibold text-slate-900">{formatRawDays(expectedConfig.summaryValue)}天</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">任务分配差值</div>
            <div className={`mt-2 text-3xl font-semibold ${teamHoursSummary.allocationDelta >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {teamHoursSummary.allocationDelta > 0 ? '+' : ''}
              {formatRawDays(teamHoursSummary.allocationDelta)}天
            </div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">任务完成差值</div>
            <div className={`mt-2 text-3xl font-semibold ${teamHoursSummary.completionDelta >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {teamHoursSummary.completionDelta > 0 ? '+' : ''}
              {formatRawDays(teamHoursSummary.completionDelta)}天
            </div>
          </Card>
        </div>
        <div className="grid gap-4 border-b border-slate-200 bg-white px-5 py-4 md:grid-cols-3">
          <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3">
            <div className="text-xs text-rose-700">分配不足人数</div>
            <div className="mt-2 text-lg font-semibold text-rose-700">{teamHoursStats.allocationRiskCount}</div>
          </div>
          <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3">
            <div className="text-xs text-amber-700">完成不足人数</div>
            <div className="mt-2 text-lg font-semibold text-amber-700">{teamHoursStats.completionRiskCount}</div>
          </div>
          <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3">
            <div className="text-xs text-rose-700">高风险人数</div>
            <div className="mt-2 text-lg font-semibold text-rose-700">{teamHoursStats.highRiskCount}</div>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">姓名</th>
                <th className="px-5 py-4 text-left font-medium">岗位</th>
                <th className="border-t-4 border-violet-400 bg-violet-100 px-5 py-4 text-left font-semibold text-violet-900">{expectedConfig.label}</th>
                <th className="border-t-4 border-sky-400 bg-sky-100 px-5 py-4 text-left font-semibold text-sky-900">当前已排总有效工时</th>
                <th className="border-t-4 border-emerald-400 bg-emerald-100 px-5 py-4 text-left font-semibold text-emerald-900">当前已完成有效工时</th>
                <th className="border-t-4 border-amber-400 bg-amber-100 px-5 py-4 text-left font-semibold text-amber-900">季度逾期总有效工时</th>
                <th className="border-t-4 border-rose-400 bg-rose-100 px-5 py-4 text-left font-semibold text-rose-900">季度逾期完成工时</th>
                <th className="px-5 py-4 text-left font-medium">
                  <div className="flex items-center gap-1">
                    任务分配差值
                    <span className="group relative cursor-help text-slate-400">
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" /></svg>
                      <span className="pointer-events-none absolute top-full left-1/2 z-20 mt-1 hidden -translate-x-1/2 rounded-lg bg-slate-800 px-3 py-2 text-[11px] leading-relaxed font-normal text-white shadow-lg group-hover:block">
                        <RiskExplanation metric="已排工时 / 季度预期有效工时" />
                      </span>
                    </span>
                  </div>
                </th>
                <th className="px-5 py-4 text-left font-medium">
                  <div className="flex items-center gap-1">
                    任务完成差值
                    <span className="group relative cursor-help text-slate-400">
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" /></svg>
                      <span className="pointer-events-none absolute top-full right-0 z-20 mt-1 hidden rounded-lg bg-slate-800 px-3 py-2 text-[11px] leading-relaxed font-normal text-white shadow-lg group-hover:block">
                        <RiskExplanation metric="已完成工时 / 季度预期有效工时" />
                      </span>
                    </span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleHourRows.map((row, index) => (
                <tr key={`${row.name}-${index}`} className={`${getRiskRowClass(row.allocationRiskLevel === '高风险' ? '高风险' : row.completionRiskLevel)} ${index !== visibleHourRows.length - 1 ? 'border-b border-slate-100' : ''}`}>
                  <td className="px-5 py-4 font-medium text-slate-900">
                    <Link
                      to={`${ROUTE_PATHS.PERSONAL_HOURS}?target=${encodeURIComponent(row.userId || row.name)}`}
                      className="text-sky-700 underline-offset-2 hover:underline"
                    >
                      {row.name}
                    </Link>
                  </td>
                  <td className="px-5 py-4 text-slate-600">{row.role}</td>
                  <td className="bg-violet-50/70 px-5 py-4 font-medium text-violet-800">{formatRawDays(row[expectedConfig.rowValue])}天</td>
                  <td className="bg-sky-50/70 px-5 py-4 font-medium text-sky-800">{formatRawDays(row.scheduledHours)}天</td>
                  <td className="bg-emerald-50/70 px-5 py-4 font-medium text-emerald-800">{formatRawDays(row.completedHours)}天</td>
                  <td className="bg-amber-50/70 px-5 py-4 font-medium text-amber-800">{formatRawDays(row.overdueEffectiveHours)}天</td>
                  <td className="bg-rose-50/70 px-5 py-4 font-medium text-rose-800">{formatRawDays(row.overdueCompletedHours)}天</td>
                  <td className="px-5 py-4">
                    <div className={`flex items-center gap-2 font-medium ${row.allocationInsufficient ? 'text-rose-700' : 'text-emerald-700'}`}>
                      <span>{row.allocationDelta > 0 ? '+' : ''}{formatRawDays(row.allocationDelta)}天</span>
                      <span className={`rounded-full px-2 py-1 text-xs ${getRiskTagClass(row.allocationRiskLevel)}`}>{row.allocationRiskLevel}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <div className={`flex items-center gap-2 font-medium ${row.completionInsufficient ? 'text-rose-700' : 'text-emerald-700'}`}>
                      <span>{row.completionDelta > 0 ? '+' : ''}{formatRawDays(row.completionDelta)}天</span>
                      <span className={`rounded-full px-2 py-1 text-xs ${getRiskTagClass(row.completionRiskLevel)}`}>{row.completionRiskLevel}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card> : null}

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">绩效情况</div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-4">
          <div className="grid gap-3 xl:grid-cols-[220px_max-content]">
            <select
              value={performanceMemberFilter}
              onChange={(event) => setPerformanceMemberFilter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
              {memberOptions.map((member) => (
                <option key={member} value={member}>{member === '全部' ? '全部成员' : member}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={handlePerformanceQuery}
              disabled={perfLoading}
              className="w-fit justify-self-start rounded-full bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {perfLoading ? '查询中...' : '查询'}
            </button>
          </div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-5">
          <div className="h-[450px] min-w-0">
            {perfLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">正在加载团队趋势...</div>
            ) : performanceTrendChart.members.length > 0 ? (
              <TeamPerformanceTrendChart
                data={performanceTrendChart.data}
                members={performanceTrendChart.members}
              />
            ) : (
              <div className="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-500">
                当前筛选条件下暂无绩效趋势数据
              </div>
            )}
          </div>
        </div>
      </Card>

    </ManagerLayout>
  );
}
