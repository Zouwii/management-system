import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import PerfImportModal from '../components/PerfImportModal';
import SectionTitle from '../components/SectionTitle';
import ManagerLayout from '../layouts/ManagerLayout';
import {
  fetchAttendance,
  fetchIntegrationTeamDetail,
  fetchNavTeamDetail,
  fetchWorkdays,
} from '../api/dashboard';
import { useAuthStore } from '../store/authStore';

function generateQuarterOptions() {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentQuarter = Math.floor(now.getMonth() / 3) + 1;
  const options = [];

  for (let year = 2025; year <= currentYear; year += 1) {
    const lastQuarter = year === currentYear ? currentQuarter : 4;
    for (let quarter = 1; quarter <= lastQuarter; quarter += 1) {
      const startMonth = (quarter - 1) * 3 + 1;
      const endMonth = startMonth + 2;
      const endDate = new Date(year, endMonth, 0);
      options.push({
        value: `${year}Q${quarter}`,
        label: `${year}年 Q${quarter}`,
        start: `${year}-${String(startMonth).padStart(2, '0')}-01T00:00:00`,
        end: `${year}-${String(endMonth).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}T23:59:59`,
      });
    }
  }

  return options.reverse();
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDays(value) {
  return toNumber(value).toFixed(2);
}

function getPerformanceTone(performance) {
  if (performance == null) {
    return { text: 'text-slate-500', bg: 'bg-slate-100', bar: 'bg-slate-300' };
  }
  if (performance >= 1) {
    return { text: 'text-emerald-700', bg: 'bg-emerald-50', bar: 'bg-emerald-500' };
  }
  if (performance >= 0.8) {
    return { text: 'text-amber-700', bg: 'bg-amber-50', bar: 'bg-amber-500' };
  }
  return { text: 'text-rose-700', bg: 'bg-rose-50', bar: 'bg-rose-500' };
}

const QUARTER_OPTIONS = generateQuarterOptions();

export default function QuarterlyEffectivePerformancePage() {
  const user = useAuthStore((state) => state.user);
  const [quarter, setQuarter] = useState(QUARTER_OPTIONS[0]?.value || '');
  const [teamFilter, setTeamFilter] = useState('ALL');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [importOpen, setImportOpen] = useState(false);

  const quarterOption = useMemo(
    () => QUARTER_OPTIONS.find((option) => option.value === quarter) || QUARTER_OPTIONS[0],
    [quarter],
  );

  const loadPerformance = useCallback(async () => {
    if (!quarterOption) return;

    setLoading(true);
    setError(null);
    const params = {
      startDate: quarterOption.start,
      endDate: quarterOption.end,
    };
    const payload = {
      start_time: quarterOption.start,
      end_time: quarterOption.end,
    };

    try {
      const [navResponse, integrationResponse, workdayResponse, attendanceResponse] = await Promise.all([
        fetchNavTeamDetail(user, params),
        fetchIntegrationTeamDetail(user, params),
        fetchWorkdays(payload),
        fetchAttendance(payload),
      ]);

      const workdayResult = workdayResponse?.data || {};
      const standardDays = toNumber(
        workdayResult.workday_count
        ?? workdayResult.effective_workday_count
        ?? workdayResult.workdays,
      );
      const attendanceMap = new Map(
        (attendanceResponse?.data?.records || []).map((record) => [String(record.user_id), record]),
      );

      const teamRows = [
        ...(navResponse?.data?.rows || []).map((row) => ({ ...row, teamCode: 'NAV', teamName: row.teamName || '导航组' })),
        ...(integrationResponse?.data?.rows || []).map((row) => ({ ...row, teamCode: 'INTEGRATION', teamName: row.teamName || '对接组' })),
      ];
      const resultMap = new Map();

      teamRows.forEach((row, index) => {
        const userId = String(row.userId || row.id || '');
        const name = row.name || row.userName || userId || `成员${index + 1}`;
        const record = attendanceMap.get(userId);
        const storedEffectiveHours = toNumber(record?.effective_work_days);
        const totalEffectiveHours = storedEffectiveHours > 0 ? storedEffectiveHours : standardDays;
        const completedCurrentHours = toNumber(row.completedHours ?? row.completedEffectiveHours);
        const completedOverdueHours = toNumber(row.overdueCompletedHours ?? row.completedOverdueEffectiveHours);
        const completedEffectiveHours = completedCurrentHours + completedOverdueHours;
        const performance = totalEffectiveHours > 0
          ? completedEffectiveHours / totalEffectiveHours
          : null;
        const key = userId || `${row.teamCode || ''}:${name}`;

        resultMap.set(key, {
          userId,
          name,
          teamCode: row.teamCode,
          teamName: row.teamName || '未分组',
          completedCurrentHours,
          completedOverdueHours,
          completedEffectiveHours,
          totalEffectiveHours,
          performance,
        });
      });

      setRows(
        Array.from(resultMap.values()).sort((left, right) => (
          left.teamName.localeCompare(right.teamName, 'zh-CN')
          || left.name.localeCompare(right.name, 'zh-CN')
        )),
      );
    } catch (loadError) {
      console.error('季度有效工时绩效加载失败:', loadError);
      setRows([]);
      setError(loadError?.message || '季度有效工时绩效加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [quarterOption, user]);

  useEffect(() => {
    loadPerformance();
  }, [loadPerformance]);

  const teamOptions = useMemo(() => [
    { code: 'ALL', label: '全部团队' },
    ...Array.from(new Map(
      rows.filter((row) => row.teamCode).map((row) => [row.teamCode, {
        code: row.teamCode,
        label: row.teamName || row.teamCode,
      }]),
    ).values()),
  ], [rows]);

  const visibleRows = useMemo(() => (
    teamFilter === 'ALL'
      ? rows
      : rows.filter((row) => row.teamCode === teamFilter)
  ), [rows, teamFilter]);

  const summary = useMemo(() => {
    const completedEffectiveHours = visibleRows.reduce(
      (sum, row) => sum + row.completedEffectiveHours,
      0,
    );
    const totalEffectiveHours = visibleRows.reduce(
      (sum, row) => sum + row.totalEffectiveHours,
      0,
    );
    const validRows = visibleRows.filter((row) => row.performance != null);
    const averagePerformance = validRows.length > 0
      ? validRows.reduce((sum, row) => sum + row.performance, 0) / validRows.length
      : null;

    return {
      memberCount: visibleRows.length,
      completedEffectiveHours,
      totalEffectiveHours,
      averagePerformance,
    };
  }, [visibleRows]);

  return (
    <ManagerLayout>
      <SectionTitle title="季度绩效" />

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
          {error}
          <button type="button" onClick={loadPerformance} className="ml-4 underline hover:text-rose-900">
            重试
          </button>
        </div>
      ) : null}

      <Card className="overflow-hidden p-0">
        <div className="bg-gradient-to-r from-slate-50 via-white to-indigo-50/70 px-6 py-6 text-slate-900">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-xl font-semibold">季度有效工时绩效</div>
            </div>
            <div className="flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center xl:w-auto">
              <button
                type="button"
                onClick={() => setImportOpen(true)}
                className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800"
              >
                导入/编辑绩效
              </button>
              <label className="flex items-center gap-3">
                <span className="font-medium text-slate-600">统计季度</span>
                <select
                  value={quarter}
                  onChange={(event) => setQuarter(event.target.value)}
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 outline-none shadow-sm focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 sm:w-[180px] sm:flex-none"
                >
                  {QUARTER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-2">
            {teamOptions.map((team) => {
              const active = teamFilter === team.code;
              return (
                <button
                  key={team.code}
                  type="button"
                  onClick={() => setTeamFilter(team.code)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    active
                      ? 'bg-slate-900 text-white shadow-sm'
                      : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  {team.label}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-3xl border border-sky-100 bg-gradient-to-br from-white to-sky-50 p-5 shadow-sm">
          <div className="text-sm font-medium text-sky-700">参与成员</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">{summary.memberCount}</div>
        </div>
        <div className="rounded-3xl border border-emerald-100 bg-gradient-to-br from-white to-emerald-50 p-5 shadow-sm">
          <div className="text-sm font-medium text-emerald-700">完成有效工时</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">{formatDays(summary.completedEffectiveHours)}</div>
        </div>
        <div className="rounded-3xl border border-indigo-100 bg-gradient-to-br from-white to-indigo-50 p-5 shadow-sm">
          <div className="text-sm font-medium text-indigo-700">总有效工时</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">{formatDays(summary.totalEffectiveHours)}</div>
        </div>
        <div className="rounded-3xl border border-violet-100 bg-gradient-to-br from-white to-violet-50 p-5 shadow-sm">
          <div className="text-sm font-medium text-violet-700">平均有效工时绩效</div>
          <div className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">
            {summary.averagePerformance == null ? '-' : summary.averagePerformance.toFixed(2)}
          </div>
        </div>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="border-b border-slate-200 bg-white px-6 py-5">
          <div className="text-lg font-semibold text-slate-900">成员绩效明细</div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50/80 text-slate-600">
              <tr>
                <th className="px-5 py-4 text-left font-medium">成员</th>
                <th className="px-5 py-4 text-center font-medium">所属团队</th>
                <th className="bg-emerald-50/60 px-5 py-4 text-center font-medium text-emerald-700">已完成有效工时</th>
                <th className="bg-amber-50/60 px-5 py-4 text-center font-medium text-amber-700">逾期完成有效工时</th>
                <th className="px-5 py-4 text-center font-medium">完成有效工时</th>
                <th className="px-5 py-4 text-center font-medium">总有效工时</th>
                <th className="bg-violet-50 px-5 py-4 text-center font-medium text-violet-700">有效工时绩效</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-slate-400">加载中...</td></tr>
              ) : visibleRows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-slate-400">暂无数据</td></tr>
              ) : visibleRows.map((row) => {
                const tone = getPerformanceTone(row.performance);
                const progress = row.performance == null ? 0 : Math.min(row.performance * 100, 100);
                return (
                  <tr key={row.userId || `${row.teamName}-${row.name}`} className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/80">
                    <td className="px-5 py-4 font-semibold text-slate-900">{row.name}</td>
                    <td className="px-5 py-4 text-center">
                      <span className="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
                        {row.teamName}
                      </span>
                    </td>
                    <td className="bg-emerald-50/30 px-5 py-4 text-center tabular-nums text-slate-700">{formatDays(row.completedCurrentHours)}</td>
                    <td className="bg-amber-50/30 px-5 py-4 text-center tabular-nums text-slate-700">{formatDays(row.completedOverdueHours)}</td>
                    <td className="px-5 py-4 text-center font-semibold tabular-nums text-emerald-700">{formatDays(row.completedEffectiveHours)}</td>
                    <td className="px-5 py-4 text-center font-medium tabular-nums text-slate-700">{formatDays(row.totalEffectiveHours)}</td>
                    <td className="bg-violet-50/40 px-5 py-4">
                      <div className="flex min-w-[150px] items-center gap-3">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
                          <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${progress}%` }} />
                        </div>
                        <span className={`min-w-[52px] rounded-lg px-2 py-1 text-center font-semibold tabular-nums ${tone.bg} ${tone.text}`}>
                          {row.performance == null ? '-' : row.performance.toFixed(2)}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <PerfImportModal open={importOpen} onClose={() => setImportOpen(false)} />
    </ManagerLayout>
  );
}
