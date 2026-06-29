import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Card from './Card';
import SectionTitle from './SectionTitle';
import ManagerLayout from '../layouts/ManagerLayout';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { formatDateTime } from '../utils/workHours';
import { fetchMembers, fetchTeamPerformance } from '../api/dashboard';
import { shouldHideMemberInSelector } from '../utils/memberVisibility';

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
  if (score >= 1.0) {
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

function normalizeHoursRows(rows) {
  return rows.map((row) => {
    const quarterExpectedHours = Number(row.quarterExpectedHours || 0);
    const currentExpectedHours = Number(row.currentExpectedHours || row.quarterExpectedHours || 0);
    const scheduledHours = Number(row.scheduledHours || 0);
    const completedHours = Number(row.completedHours || 0);
    const overdueEffectiveHours = Number(row.overdueEffectiveHours || 0);
    const overdueCompletedHours = Number(row.overdueCompletedHours || 0);
    const allocationActualHours = scheduledHours;
    const completionActualHours = completedHours;
    const allocationDelta = Number.isFinite(Number(row.allocationDelta))
      ? Number(row.allocationDelta)
      : (scheduledHours - quarterExpectedHours);
    const completionDelta = Number.isFinite(Number(row.completionDelta))
      ? Number(row.completionDelta)
      : (completedHours - quarterExpectedHours);
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

function buildPerformanceRows(rows, quarter) {
  return rows.map((row) => {
    const finalScore = Number(row.finalScore);
    const carryScore = Number(row.carryScore);
    const score = Number.isFinite(finalScore) ? finalScore : 0;
    return {
      ...row,
      quarter: row.quarter || quarter,
      finalScore: score,
      carryScore: Number.isFinite(carryScore) ? carryScore : 0,
      band: Number.isFinite(finalScore) ? getPerformanceBand(score) : '-',
      performanceRisk: Number.isFinite(finalScore) ? score < 1.0 : false,
    };
  });
}

function getCurrentQuarterLabel() {
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  return `${now.getFullYear()}Q${q}`;
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

export default function TeamDetailDashboard({
  title,
  desc,
  teamKey,
  fetcher,
  fallbackRows,
}) {
  const user = useAuthStore((state) => state.user);
  const [searchParams] = useSearchParams();
  const initialExpectedParam = searchParams.get('expected');
  const initialExpectedView = ['quarter', 'current', 'last_quarter'].includes(initialExpectedParam)
    ? initialExpectedParam
    : 'quarter';
  const initialHoursAbnormal = ({
    abnormal: '只看异常成员',
    allocation: '只看分配不足',
    completion: '只看完成不足',
  })[searchParams.get('hoursAbnormal') || ''] ?? '全部成员';
  const initialPerformanceScore = ({
    below: '低于1.0',
    mid: '1.0-1.2',
    high: '1.2及以上',
  })[searchParams.get('performanceScore') || ''] ?? '全部绩效';
  const [rows, setRows] = useState(fallbackRows);
  const [memberOptions, setMemberOptions] = useState(['全部', ...fallbackRows.map((row) => row.name)]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [hoursMemberFilter, setHoursMemberFilter] = useState('全部');
  const [hoursAbnormalFilter, setHoursAbnormalFilter] = useState(initialHoursAbnormal);
  const [allocationSort, setAllocationSort] = useState('none');
  const [completionSort, setCompletionSort] = useState('none');
  const [expectedView, setExpectedView] = useState(initialExpectedView);
  const [performanceMemberFilter, setPerformanceMemberFilter] = useState('全部');
  const [performanceScoreFilter, setPerformanceScoreFilter] = useState(initialPerformanceScore);
  const performanceQuarters = useMemo(() => generateQuarterOptions(), []);
  const defaultQuarter = useMemo(() => getDefaultQuarter(), []);
  const [selectedQuarter, setSelectedQuarter] = useState(defaultQuarter);
  const [appliedQuarter, setAppliedQuarter] = useState(defaultQuarter);
  const [performanceData, setPerformanceData] = useState([]);
  const [perfLoading, setPerfLoading] = useState(false);

  // 切换季度时拉取绩效数据
  useEffect(() => {
    let active = true;
    const parsed = parseQuarterLabel(appliedQuarter);
    if (!parsed || !teamKey) return;

    setPerfLoading(true);
    fetchTeamPerformance(user, {
      year: parsed.year,
      quarter: parsed.quarter,
      teamKey,
    }).then((res) => {
      if (!active) return;
      setPerformanceData(res?.data?.results ?? []);
      setPerfLoading(false);
    }).catch(() => {
      if (!active) return;
      setPerformanceData([]);
      setPerfLoading(false);
    });

    return () => { active = false; };
  }, [appliedQuarter, teamKey, user]);

  // 工时数据加载
  useEffect(() => {
    let active = true;

    fetcher(user, { expected: expectedView }).then((response) => {
      if (!active) {
        return;
      }

      const nextRows = response.data.rows ?? fallbackRows;
      setRows(nextRows);
      setLastUpdatedAt(String(response?.data?.lastUpdatedAt || ''));
    });

    // 下拉成员列表：统一从 /perf/members?team= 获取，排除管理员
    if (teamKey) {
      fetchMembers(teamKey).then((res) => {
        if (!active) return;
        const names = (res?.data?.members || [])
          .filter((m) => !shouldHideMemberInSelector(m))
          .map((m) => m.userName)
          .filter(Boolean);
        setMemberOptions(names.length ? ['全部', ...names] : ['全部']);
      }).catch(() => {});
    }

    return () => {
      active = false;
    };
  }, [expectedView, fallbackRows, fetcher, teamKey, user]);

  useEffect(() => {
    const nextExpectedView = searchParams.get('expected') === 'current' ? 'current' : 'quarter';
    const nextHoursAbnormal = ({
      abnormal: '只看异常成员',
      allocation: '只看分配不足',
      completion: '只看完成不足',
    })[searchParams.get('hoursAbnormal') || ''] ?? '全部成员';
    const nextPerformanceScore = ({
      below: '低于1.0',
      mid: '1.0-1.2',
      high: '1.2及以上',
    })[searchParams.get('performanceScore') || ''] ?? '全部绩效';

    setExpectedView(nextExpectedView);
    setHoursAbnormalFilter(nextHoursAbnormal);
    setPerformanceScoreFilter(nextPerformanceScore);
  }, [searchParams]);

  useEffect(() => {
    if (memberOptions.includes(hoursMemberFilter)) return;
    setHoursMemberFilter('全部');
  }, [hoursMemberFilter, memberOptions]);

  useEffect(() => {
    if (memberOptions.includes(performanceMemberFilter)) return;
    setPerformanceMemberFilter('全部');
  }, [memberOptions, performanceMemberFilter]);

  const allHourRows = useMemo(() => {
    const normalized = normalizeHoursRows(rows);
    return normalized.map((row) => ({
      ...row,
      selectedExpectedHours: row.quarterExpectedHours,
      allocationInsufficient: row.allocationDelta < 0,
      completionInsufficient: row.completionDelta < 0,
      allocationRiskLevel: getRiskLevel(row.scheduledHours, row.quarterExpectedHours),
      completionRiskLevel: getRiskLevel(row.completedHours, row.quarterExpectedHours),
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

  const visiblePerformanceRows = useMemo(() => {
    // 将 API 返回的绩效数据与 rows 做 join（rows 有 userName / role）
    const rowMap = {};
    rows.forEach((r) => {
      rowMap[String(r.userId || '')] = r;
    });

    let perfRows = performanceData.map((p) => {
      const info = rowMap[String(p.userId || '')] || {};
      const score = Number(p.finalScore);
      return {
        userId: p.userId,
        name: info.name || info.userName || p.userId,
        role: info.role || '-',
        quarter: `${p.year}Q${p.quarter}`,
        finalScore: Number.isFinite(score) ? score : 0,
        band: Number.isFinite(score) ? getPerformanceBand(score) : '-',
        carryScore: Number(p.newCarryBalance || 0),
        performanceRisk: Number.isFinite(score) ? score < 1.0 : false,
      };
    });

    // 过滤
    return perfRows.filter((row) => {
      if (performanceMemberFilter !== '全部' && row.name !== performanceMemberFilter) {
        return false;
      }
      if (performanceScoreFilter === '低于1.0') {
        return row.finalScore < 1.0;
      }
      if (performanceScoreFilter === '1.0-1.2') {
        return row.finalScore >= 1.0 && row.finalScore < 1.2;
      }
      if (performanceScoreFilter === '1.2及以上') {
        return row.finalScore >= 1.2;
      }
      return true;
    });
  }, [performanceData, rows, performanceMemberFilter, performanceScoreFilter]);

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
  const avgFinalPerformance = visiblePerformanceRows.length
    ? (visiblePerformanceRows.reduce((sum, row) => sum + row.finalScore, 0) / visiblePerformanceRows.length).toFixed(2)
    : '0.00';
  const expectedConfig = expectedView === 'current'
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

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">工时情况</div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-4">
          <div className="grid gap-3 xl:grid-cols-[repeat(4,minmax(0,1fr))_auto]">
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
                <span className="whitespace-nowrap text-sm text-slate-500">时间范围</span>
                <select
                  value={expectedView}
                  onChange={(event) => setExpectedView(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none"
                >
                  <option value="quarter">本季度</option>
                  <option value="current">本季度至今天</option>
                  <option value="last_quarter">上季度</option>
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
                <th className="px-5 py-4 text-left font-medium">{expectedConfig.label}</th>
                <th className="px-5 py-4 text-left font-medium">当前已排总有效工时</th>
                <th className="px-5 py-4 text-left font-medium">当前已完成有效工时</th>
                <th className="px-5 py-4 text-left font-medium">季度逾期总有效工时</th>
                <th className="px-5 py-4 text-left font-medium">季度逾期完成工时</th>
                <th className="px-5 py-4 text-left font-medium">任务分配差值</th>
                <th className="px-5 py-4 text-left font-medium">任务完成差值</th>
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
                  <td className="px-5 py-4 text-slate-600">{formatRawDays(row[expectedConfig.rowValue])}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatRawDays(row.scheduledHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatRawDays(row.completedHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatRawDays(row.overdueEffectiveHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatRawDays(row.overdueCompletedHours)}天</td>
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
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">绩效情况</div>
          <div className="mt-1 text-sm text-slate-500">按季度查看每个成员的绩效结果，默认展示当前最新季度。</div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-4">
          <div className="grid gap-3 xl:grid-cols-[220px_180px_180px_auto_auto]">
            <select
              value={performanceMemberFilter}
              onChange={(event) => setPerformanceMemberFilter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
              {memberOptions.map((member) => (
                <option key={member} value={member}>{member === '全部' ? '全部成员' : member}</option>
              ))}
            </select>
            <select
              value={selectedQuarter}
              onChange={(event) => setSelectedQuarter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
              {performanceQuarters.map((quarter) => (
                <option key={quarter} value={quarter}>{quarter}</option>
              ))}
            </select>
            <select
              value={performanceScoreFilter}
              onChange={(event) => setPerformanceScoreFilter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
              <option value="全部绩效">全部绩效</option>
              <option value="低于1.0">低于 1.0</option>
              <option value="1.0-1.2">1.0 - 1.2</option>
              <option value="1.2及以上">1.2 及以上</option>
            </select>
            <button
              type="button"
              onClick={() => setAppliedQuarter(selectedQuarter)}
              disabled={perfLoading}
              className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {perfLoading ? '查询中...' : '查询季度'}
            </button>
            <div className="flex items-center justify-end text-sm text-slate-500">
              平均最终绩效
              {' '}
              <span className="ml-1 font-semibold text-slate-900">{avgFinalPerformance}</span>
            </div>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">姓名</th>
                <th className="px-5 py-4 text-left font-medium">岗位</th>
                <th className="px-5 py-4 text-left font-medium">季度</th>
                <th className="px-5 py-4 text-left font-medium">最终绩效</th>
                <th className="px-5 py-4 text-left font-medium">档位</th>
                <th className="px-5 py-4 text-left font-medium">本季度结余</th>
              </tr>
            </thead>
            <tbody>
              {visiblePerformanceRows.map((row, index) => (
                <tr key={`${row.name}-${index}`} className={index !== visiblePerformanceRows.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-5 py-4 font-medium text-slate-900">{row.name}</td>
                  <td className="px-5 py-4 text-slate-600">{row.role}</td>
                  <td className="px-5 py-4 text-slate-600">{row.quarter}</td>
                  <td className={`px-5 py-4 font-medium ${row.performanceRisk ? 'text-rose-700' : 'text-emerald-700'}`}>{row.finalScore.toFixed(2)}</td>
                  <td className="px-5 py-4 text-slate-600">{row.band}</td>
                  <td className="px-5 py-4 text-slate-600">{row.carryScore.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

    </ManagerLayout>
  );
}
