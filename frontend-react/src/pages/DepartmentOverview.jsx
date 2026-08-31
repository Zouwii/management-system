import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchDepartmentOverview } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import { ROUTE_PATHS } from '../constants/routes';
import ManagerLayout from '../layouts/ManagerLayout';
import { departmentStats as fallbackStats } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';
import { formatDateTime } from '../utils/workHours';

function getQuarterLabel(year, quarter) {
  return `${year} Q${quarter}`;
}

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function parsePercent(value, fallback = 100) {
  if (typeof value === 'string') {
    const number = Number(value.replace('%', ''));
    return Number.isFinite(number) ? number : fallback;
  }
  return toNumber(value, fallback);
}

function getMemberName(row) {
  return row.userName || row.name || row.memberName || '-';
}

function getTeamName(row) {
  return row.team || row.teamName || row.teamLabel || '-';
}

function getExpectedHours(row) {
  return toNumber(row.expectedEffectiveHours ?? row.quarterExpectedHours ?? row.expectedHours ?? row.hours, 0);
}

function getScheduledHours(row) {
  return toNumber(row.scheduledHours ?? row.scheduledEffectiveHours ?? row.hours, 0)
    + toNumber(row.overdueHours ?? row.quarterlyOverdueEffectiveHours, 0);
}

function getCompletedHours(row) {
  const expectedHours = getExpectedHours(row);
  const fromRate = row.effectiveRate !== undefined
    ? expectedHours * parsePercent(row.effectiveRate, 100) / 100
    : null;

  return toNumber(row.completedHours ?? row.completedEffectiveHours ?? row.costHour ?? fromRate ?? row.hours, 0)
    + toNumber(row.overdueCompletedHours ?? row.quarterlyOverdueCompletedHours, 0);
}

function getPrevFinalScore(row) {
  return toNumber(row.prevFinalScore ?? row.finalScore ?? row.finalPerformance, 0);
}

function getCurrentFinalScore(row) {
  return toNumber(row.currentFinalScore ?? 0);
}

function formatHours(value) {
  return toNumber(value).toFixed(1);
}

function formatScore(value) {
  const score = toNumber(value);
  return score > 0 ? score.toFixed(2) : '-';
}

function formatDateTimeInput(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function getCurrentQuarterRange() {
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  return {
    startDate: formatDateTimeInput(new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0)),
    endDate: formatDateTimeInput(new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59)),
  };
}

function getFullQuarterRange() {
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  return {
    startDate: formatDateTimeInput(new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0)),
    endDate: formatDateTimeInput(new Date(now.getFullYear(), quarterStartMonth + 3, 0, 23, 59, 59)),
  };
}

function getLastQuarterRange() {
  const now = new Date();
  const currentQuarter = Math.floor(now.getMonth() / 3);
  const lastQuarterStartMonth = currentQuarter === 0 ? 9 : (currentQuarter - 1) * 3;
  const lastQuarterYear = currentQuarter === 0 ? now.getFullYear() - 1 : now.getFullYear();
  return {
    startDate: formatDateTimeInput(new Date(lastQuarterYear, lastQuarterStartMonth, 1, 0, 0, 0)),
    endDate: formatDateTimeInput(new Date(lastQuarterYear, lastQuarterStartMonth + 3, 0, 23, 59, 59)),
  };
}

const TIME_PRESETS = [
  { key: 'last_quarter', label: '上季度', get: getLastQuarterRange },
  { key: 'quarter', label: '本季度', get: getFullQuarterRange },
  { key: 'quarter_to_today', label: '本季度至今天', get: getCurrentQuarterRange },
];

const TEAM_BAND_STYLES = {
  对接组: {
    band: 'border-violet-500 bg-gradient-to-r from-violet-100 via-violet-50 to-white',
    dot: 'bg-violet-500',
    title: 'text-violet-950',
    count: 'border-violet-200 bg-white/80 text-violet-700',
  },
  导航组: {
    band: 'border-sky-500 bg-gradient-to-r from-sky-100 via-sky-50 to-white',
    dot: 'bg-sky-500',
    title: 'text-sky-950',
    count: 'border-sky-200 bg-white/80 text-sky-700',
  },
};

const DEFAULT_TEAM_BAND_STYLE = {
  band: 'border-slate-400 bg-gradient-to-r from-slate-100 via-slate-50 to-white',
  dot: 'bg-slate-400',
  title: 'text-slate-900',
  count: 'border-slate-200 bg-white/80 text-slate-600',
};

function buildMemberRows(rows) {
  return rows.map((row) => {
    const expectedHours = getExpectedHours(row);
    const scheduledHours = getScheduledHours(row);
    const completedHours = getCompletedHours(row);
    const prevFinalScore = getPrevFinalScore(row);
    const currentFinalScore = getCurrentFinalScore(row);
    const allocationGap = scheduledHours - expectedHours;
    const completionGap = completedHours - expectedHours;

    return {
      name: getMemberName(row),
      team: getTeamName(row),
      role: row.role || row.position || row.jobTitle || '-',
      expectedHours,
      scheduledHours,
      completedHours,
      prevFinalScore,
      currentFinalScore,
      allocationGap,
      completionGap,
    };
  });
}

function getGapClass(value) {
  if (value < 0) return 'text-rose-700';
  if (value > 0) return 'text-emerald-700';
  return 'text-slate-700';
}

function groupByTeam(memberRows) {
  return memberRows.reduce((groups, row) => {
    const key = row.team || '-';
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
    return groups;
  }, {});
}

function buildTeamSummary(label, rows, route) {
  const expectedHours = rows.reduce((sum, row) => sum + row.expectedHours, 0);
  const scheduledHours = rows.reduce((sum, row) => sum + row.scheduledHours, 0);
  const completedHours = rows.reduce((sum, row) => sum + row.completedHours, 0);
  const allocationGap = scheduledHours - expectedHours;
  const completionGap = completedHours - expectedHours;
  const allocationRate = expectedHours > 0 ? Math.round((scheduledHours / expectedHours) * 100) : 0;
  const completionRate = expectedHours > 0 ? Math.round((completedHours / expectedHours) * 100) : 0;

  return {
    label,
    route,
    expectedHours,
    scheduledHours,
    completedHours,
    allocationGap,
    completionGap,
    allocationRate,
    completionRate,
  };
}

function getProgressWidth(value) {
  return `${Math.max(0, Math.min(value, 120))}%`;
}

function sortRows(rows, sortConfig) {
  if (!sortConfig.key) return rows;
  const direction = sortConfig.direction === 'asc' ? 1 : -1;
  return [...rows].sort((left, right) => {
    const leftValue = toNumber(left[sortConfig.key]);
    const rightValue = toNumber(right[sortConfig.key]);
    return (leftValue - rightValue) * direction;
  });
}

const SORT_OPTIONS = [
  { key: '', label: '默认' },
  { key: 'allocationGap', label: '分配差额' },
  { key: 'completionGap', label: '完成差额' },
];

export default function DepartmentOverview() {
  const user = useAuthStore((state) => state.user);
  const [rows, setRows] = useState([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [apiQuarter, setApiQuarter] = useState(null);
  const [dateRange, setDateRange] = useState(() => getCurrentQuarterRange());
  const [timePreset, setTimePreset] = useState('quarter_to_today');
  const [showPerformance, setShowPerformance] = useState(false);
  const [sortConfig, setSortConfig] = useState({ key: '', direction: 'asc' });

  useEffect(() => {
    let active = true;

    fetchDepartmentOverview(user, dateRange).then((response) => {
      if (!active) return;
      const data = response?.data ?? {};
      setRows(data.rows ?? []);
      setLastUpdatedAt(data.lastUpdatedAt || new Date().toISOString());
      setApiQuarter(data.quarter ?? null);
    }).catch(() => {});

    return () => {
      active = false;
    };
  }, [dateRange, user]);

  const quarterLabel = apiQuarter
    ? getQuarterLabel(apiQuarter.year, apiQuarter.quarter)
    : fallbackStats.quarter ?? '2026 Q2';

  const memberRows = useMemo(() => buildMemberRows(rows), [rows]);
  const teamGroups = useMemo(() => groupByTeam(memberRows), [memberRows]);
  const teamSummaries = useMemo(() => {
    const navRows = teamGroups['导航组'] ?? [];
    const integrationRows = teamGroups['对接组'] ?? [];

    return [
      buildTeamSummary('对接组', integrationRows, ROUTE_PATHS.INTEGRATION_TEAM_DETAIL),
      buildTeamSummary('导航组', navRows, ROUTE_PATHS.NAV_TEAM_DETAIL),
    ];
  }, [teamGroups]);
  const summary = useMemo(() => {
    const totalScheduledHours = memberRows.reduce((sum, row) => sum + row.scheduledHours, 0);

    return {
      totalScheduledHours,
    };
  }, [memberRows]);
  const setSortKey = (key) => {
    setSortConfig((prev) => ({
      key,
      direction: key ? prev.direction || 'asc' : 'asc',
    }));
  };
  const toggleSortDirection = () => {
    setSortConfig((prev) => ({
      ...prev,
      direction: prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  return (
    <ManagerLayout>
      <SectionTitle
        title="部门有效工时"
        right={(
          <div className="flex flex-wrap justify-end gap-2 text-sm">
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">{quarterLabel}</div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">同步：{lastUpdatedAt ? formatDateTime(lastUpdatedAt) : '暂无'}</div>
          </div>
        )}
      />

      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-slate-900">筛选时间</div>
          </div>
          <div className="flex w-full flex-wrap items-center gap-3 md:w-auto">
            <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
              <span className="shrink-0">开始时间</span>
              <input
                type="datetime-local"
                step="1"
                value={dateRange.startDate}
                onChange={(event) => setDateRange((prev) => ({ ...prev, startDate: event.target.value }))}
                max={dateRange.endDate || undefined}
                className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none"
              />
            </label>
            <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
              <span className="shrink-0">结束时间</span>
              <input
                type="datetime-local"
                step="1"
                value={dateRange.endDate}
                onChange={(event) => setDateRange((prev) => ({ ...prev, endDate: event.target.value }))}
                min={dateRange.startDate || undefined}
                className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none"
              />
            </label>
            <div className="flex items-center gap-2">
              {TIME_PRESETS.map(({ key, label, get }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => { setTimePreset(key); setDateRange(get()); }}
                  className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium ${
                    timePreset === key
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {teamSummaries.map((team) => (
          <Card key={team.label} className="p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xl font-semibold text-slate-900">{team.label}</div>
              </div>
              <Link to={team.route} className="rounded-full border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
                明细
              </Link>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <div className="text-xs text-slate-500">应分配</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatHours(team.expectedHours)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <div className="text-xs text-slate-500">已分配</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatHours(team.scheduledHours)}</div>
              </div>
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <div className="text-xs text-slate-500">已完成</div>
                <div className="mt-1 text-xl font-semibold text-slate-900">{formatHours(team.completedHours)}</div>
              </div>
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 px-4 py-3">
                <div className="text-xs text-slate-500">任务分配差额</div>
                <div className={`mt-1 text-xl font-semibold ${getGapClass(team.allocationGap)}`}>
                  {team.allocationGap > 0 ? '+' : ''}{formatHours(team.allocationGap)}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 px-4 py-3">
                <div className="text-xs text-slate-500">任务完成差额</div>
                <div className={`mt-1 text-xl font-semibold ${getGapClass(team.completionGap)}`}>
                  {team.completionGap > 0 ? '+' : ''}{formatHours(team.completionGap)}
                </div>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              <div>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-slate-600">分配进度</span>
                  <span className="font-semibold text-slate-900">{team.allocationRate}%</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-sky-500" style={{ width: getProgressWidth(team.allocationRate) }} />
                </div>
              </div>
              <div>
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-slate-600">完成进度</span>
                  <span className="font-semibold text-slate-900">{team.completionRate}%</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-emerald-500" style={{ width: getProgressWidth(team.completionRate) }} />
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="text-lg font-semibold text-slate-900">部门成员</div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="text-sm text-slate-500">
              已排期 {formatHours(summary.totalScheduledHours)}
            </div>
            <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 p-1">
              {SORT_OPTIONS.map((option) => (
                <button
                  key={option.key || 'default'}
                  type="button"
                  onClick={() => setSortKey(option.key)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                    sortConfig.key === option.key
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={toggleSortDirection}
              disabled={!sortConfig.key}
              className={`rounded-xl border px-3 py-2 text-sm font-medium ${
                sortConfig.key
                  ? 'border-slate-200 text-slate-700 hover:bg-slate-50'
                  : 'cursor-not-allowed border-slate-100 text-slate-300'
              }`}
            >
              {sortConfig.direction === 'asc' ? '从低到高' : '从高到低'}
            </button>
            <button
              type="button"
              onClick={() => setShowPerformance((prev) => !prev)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {showPerformance ? '收起绩效' : '展开绩效'}
            </button>
          </div>
        </div>

        {Object.entries(teamGroups).map(([team, teamRows]) => {
          const sortedRows = sortRows(teamRows, sortConfig);
          const bandStyle = TEAM_BAND_STYLES[team] ?? DEFAULT_TEAM_BAND_STYLE;
          return (
            <div key={team} className="border-b border-slate-200 last:border-b-0">
              <div className={`flex items-center justify-between border-l-4 px-5 py-3.5 ${bandStyle.band}`}>
                <div className="flex items-center gap-2.5">
                  <span className={`h-2.5 w-2.5 rounded-full ${bandStyle.dot}`} aria-hidden="true" />
                  <div className={`font-semibold ${bandStyle.title}`}>{team}</div>
                </div>
                <div className={`rounded-full border px-3 py-1 text-xs font-semibold ${bandStyle.count}`}>
                  {teamRows.length} 人
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className={`${showPerformance ? 'min-w-[1050px] max-w-[1200px]' : 'min-w-[800px] max-w-[920px]'} table-fixed text-left text-sm`}>
                  <colgroup>
                    <col className="w-[14%]" />
                    <col className="w-[16%]" />
                    <col className="w-[12%]" />
                    <col className="w-[12%]" />
                    <col className="w-[14%]" />
                    <col className="w-[14%]" />
                    {showPerformance && <col className="w-[9%]" />}
                    {showPerformance && <col className="w-[9%]" />}
                  </colgroup>
                  <thead className="text-xs font-semibold uppercase text-slate-500">
                    <tr className="border-b border-slate-100">
                      <th className="pl-6 pr-4 py-3">成员</th>
                      <th className="px-4 py-3">岗位</th>
                      <th className="px-4 py-3 text-right">已排期</th>
                      <th className="px-4 py-3 text-right">已完成</th>
                      <th className="px-4 py-3 text-right">
                        分配差额{sortConfig.key === 'allocationGap' ? (sortConfig.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                      </th>
                      <th className={`${showPerformance ? 'px-4' : 'pl-4 pr-10'} py-3 text-right`}>
                        完成差额{sortConfig.key === 'completionGap' ? (sortConfig.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                      </th>
                      {showPerformance && <th className="px-3 py-3 text-right">上季绩效</th>}
                      {showPerformance && <th className="pl-3 pr-10 py-3 text-right">本季绩效</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.map((row) => (
                      <tr key={`${row.team}-${row.name}`} className="border-b border-slate-100 last:border-b-0">
                        <td className="truncate pl-6 pr-4 py-3 font-semibold text-slate-900">{row.name}</td>
                        <td className="truncate px-4 py-3 text-slate-600">{row.role}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-700">{formatHours(row.scheduledHours)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-700">{formatHours(row.completedHours)}</td>
                        <td className={`px-4 py-3 text-right font-semibold tabular-nums ${getGapClass(row.allocationGap)}`}>
                          {row.allocationGap > 0 ? '+' : ''}{formatHours(row.allocationGap)}
                        </td>
                        <td className={`${showPerformance ? 'px-4' : 'pl-4 pr-10'} py-3 text-right font-semibold tabular-nums ${getGapClass(row.completionGap)}`}>
                          {row.completionGap > 0 ? '+' : ''}{formatHours(row.completionGap)}
                        </td>
                        {showPerformance && (
                          <>
                            <td className="px-3 py-3 text-right font-semibold tabular-nums text-slate-700">{formatScore(row.prevFinalScore)}</td>
                            <td className="pl-3 pr-10 py-3 text-right font-semibold tabular-nums text-slate-900">{formatScore(row.currentFinalScore)}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </Card>
    </ManagerLayout>
  );
}
