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

function getFinalScore(row) {
  return toNumber(row.finalScore ?? row.finalPerformance, 0);
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

function formatDateInput(date) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function getCurrentQuarterRange() {
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  return {
    startDate: formatDateInput(new Date(now.getFullYear(), quarterStartMonth, 1)),
    endDate: formatDateInput(now),
  };
}

function getFullQuarterRange() {
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  return {
    startDate: formatDateInput(new Date(now.getFullYear(), quarterStartMonth, 1)),
    endDate: formatDateInput(new Date(now.getFullYear(), quarterStartMonth + 3, 0)),
  };
}

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
        desc="先按时间查看对接组和导航组的工作分配、完成情况，再看成员明细。"
        right={(
          <div className="flex flex-wrap justify-end gap-2 text-sm">
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">{quarterLabel}</div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">同步：{lastUpdatedAt ? formatDateTime(lastUpdatedAt) : '暂无'}</div>
          </div>
        )}
      />

      <Card className="p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-slate-900">筛选时间</div>
            <div className="mt-1 text-sm text-slate-500">按所选时间查看小组工作分配和完成情况。</div>
          </div>
          <div className="grid w-full gap-3 md:w-auto md:grid-cols-[180px_180px_auto_auto]">
            <label className="text-sm text-slate-600">
              <span className="mb-1 block">开始日期</span>
              <input
                type="date"
                value={dateRange.startDate}
                onChange={(event) => setDateRange((prev) => ({ ...prev, startDate: event.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400"
              />
            </label>
            <label className="text-sm text-slate-600">
              <span className="mb-1 block">结束日期</span>
              <input
                type="date"
                value={dateRange.endDate}
                onChange={(event) => setDateRange((prev) => ({ ...prev, endDate: event.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400"
              />
            </label>
            <button
              type="button"
              onClick={() => setDateRange(getCurrentQuarterRange())}
              className="self-end rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              本季度至今
            </button>
            <button
              type="button"
              onClick={() => setDateRange(getFullQuarterRange())}
              className="self-end rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              本季度
            </button>
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
            <div className="mt-1 text-sm text-slate-500">按小组查看每个人的工时；展开后显示绩效。</div>
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
          return (
            <div key={team} className="border-b border-slate-100 last:border-b-0">
              <div className="flex items-center justify-between bg-slate-50 px-5 py-3">
                <div className="font-semibold text-slate-900">{team}</div>
                <div className="text-sm text-slate-500">{teamRows.length} 人</div>
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
