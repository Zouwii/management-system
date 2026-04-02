import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Card from './Card';
import SectionTitle from './SectionTitle';
import ManagerLayout from '../layouts/ManagerLayout';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { performanceArchives, personalHoursDashboard } from '../mock/platformData';
import { getCurrentLocalDateTime } from '../utils/managerDashboard';
import { calculateExpectedEffectiveDays, formatDateTime, formatDays } from '../utils/workHours';

const BASE_REFERENCE_HOURS = 156;
const CURRENT_PROGRESS_RATIO = 0.72;

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

function buildQuickLinks(teamName) {
  return [
    { label: '部门总览', to: ROUTE_PATHS.DEPARTMENT_OVERVIEW, active: false },
    { label: '导航组', to: ROUTE_PATHS.NAV_TEAM_DETAIL, active: teamName === '导航组' },
    { label: '对接组', to: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL, active: teamName === '对接组' },
    { label: '个人', to: ROUTE_PATHS.PERSONAL_HOURS, active: false },
  ];
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

function getArchiveByIndex(row, index) {
  const templates = Object.values(performanceArchives);
  return performanceArchives[row.name] ?? templates[index % templates.length];
}

function buildHoursRows(rows) {
  const baseQuarterExpectedHours = calculateExpectedEffectiveDays(
    personalHoursDashboard.defaultRange.startDate,
    personalHoursDashboard.defaultRange.endDate,
    personalHoursDashboard.statutoryHolidays,
    personalHoursDashboard.compensatoryDays,
  ).hours;
  const baseCurrentExpectedHours = baseQuarterExpectedHours * CURRENT_PROGRESS_RATIO;

  return rows.map((row) => {
    const scale = Number(row.hours || 0) / BASE_REFERENCE_HOURS || 1;
    const quarterExpectedHours = baseQuarterExpectedHours * scale;
    const currentExpectedHours = baseCurrentExpectedHours * scale;
    const scheduledHours = Number(personalHoursDashboard.scheduledEffectiveHours || 0) * scale;
    const completedHours = Number(personalHoursDashboard.completedEffectiveHours || 0) * scale;
    const overdueEffectiveHours = Number(personalHoursDashboard.quarterlyOverdueEffectiveHours || 0) * scale;
    const overdueCompletedHours = Number(personalHoursDashboard.quarterlyOverdueCompletedHours || 0) * scale;
    return {
      ...row,
      quarterExpectedHours,
      currentExpectedHours,
      scheduledHours,
      completedHours,
      overdueEffectiveHours,
      overdueCompletedHours,
    };
  });
}

function buildDisplayedHoursRows(rows, expectedView) {
  return rows.map((row) => {
    const expectedHours = expectedView === 'current' ? row.currentExpectedHours : row.quarterExpectedHours;
    const allocationActualHours = row.scheduledHours + row.overdueEffectiveHours;
    const completionActualHours = row.completedHours + row.overdueCompletedHours;
    const allocationDelta = allocationActualHours - expectedHours;
    const completionDelta = completionActualHours - expectedHours;

    return {
      ...row,
      selectedExpectedHours: expectedHours,
      allocationActualHours,
      completionActualHours,
      allocationDelta,
      completionDelta,
      allocationInsufficient: allocationDelta < 0,
      completionInsufficient: completionDelta < 0,
      allocationRiskLevel: getRiskLevel(allocationActualHours, expectedHours),
      completionRiskLevel: getRiskLevel(completionActualHours, expectedHours),
    };
  });
}

function buildPerformanceRows(rows, quarter) {
  return rows.map((row, index) => {
    const archive = getArchiveByIndex(row, index);
    const record = archive.history.find((item) => item.quarter === quarter) ?? archive.history[archive.history.length - 1];

    return {
      ...row,
      quarter: record.quarter,
      finalScore: record.finalScore,
      carryScore: record.carryScore ?? 0,
      band: getPerformanceBand(record.finalScore),
      performanceRisk: record.finalScore < 1.0,
    };
  });
}

export default function TeamDetailDashboard({
  title,
  desc,
  teamName,
  fetcher,
  fallbackRows,
}) {
  const user = useAuthStore((state) => state.user);
  const [searchParams] = useSearchParams();
  const initialExpectedView = searchParams.get('expected') === 'current' ? 'current' : 'quarter';
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
  const [lastUpdatedAt, setLastUpdatedAt] = useState(getCurrentLocalDateTime());
  const [hoursMemberFilter, setHoursMemberFilter] = useState('全部');
  const [hoursAbnormalFilter, setHoursAbnormalFilter] = useState(initialHoursAbnormal);
  const [allocationSort, setAllocationSort] = useState('none');
  const [completionSort, setCompletionSort] = useState('none');
  const [expectedView, setExpectedView] = useState(initialExpectedView);
  const [performanceMemberFilter, setPerformanceMemberFilter] = useState('全部');
  const [performanceScoreFilter, setPerformanceScoreFilter] = useState(initialPerformanceScore);
  const performanceQuarters = useMemo(() => {
    const template = Object.values(performanceArchives)[0];
    return template?.history?.map((item) => item.quarter) ?? [];
  }, []);
  const latestQuarter = performanceQuarters[performanceQuarters.length - 1] ?? '';
  const [selectedQuarter, setSelectedQuarter] = useState(latestQuarter);
  const [appliedQuarter, setAppliedQuarter] = useState(latestQuarter);

  useEffect(() => {
    let active = true;

    fetcher(user).then((response) => {
      if (!active) {
        return;
      }

      setRows(response.data.rows ?? fallbackRows);
      setLastUpdatedAt(getCurrentLocalDateTime());
    });

    return () => {
      active = false;
    };
  }, [fallbackRows, fetcher, user]);

  useEffect(() => {
    setSelectedQuarter(latestQuarter);
    setAppliedQuarter(latestQuarter);
  }, [latestQuarter]);

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

  const memberOptions = useMemo(() => ['全部', ...rows.map((row) => row.name)], [rows]);

  const allHourRows = useMemo(() => buildDisplayedHoursRows(buildHoursRows(rows), expectedView), [expectedView, rows]);
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
    return buildPerformanceRows(rows, appliedQuarter).filter((row) => {
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
  }, [appliedQuarter, performanceMemberFilter, performanceScoreFilter, rows]);

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
    totalHours: visibleHourRows.reduce((sum, row) => sum + Number(row.hours || 0), 0),
    allocationRiskCount: visibleHourRows.filter((row) => row.allocationDelta < 0).length,
    completionRiskCount: visibleHourRows.filter((row) => row.completionDelta < 0).length,
    highRiskCount: visibleHourRows.filter((row) => row.allocationRiskLevel === '高风险' || row.completionRiskLevel === '高风险').length,
  }), [visibleHourRows]);
  const avgFinalPerformance = visiblePerformanceRows.length
    ? (visiblePerformanceRows.reduce((sum, row) => sum + row.finalScore, 0) / visiblePerformanceRows.length).toFixed(2)
    : '0.00';
  const combinedInsights = useMemo(() => visibleHourRows.reduce((accumulator, row) => {
    const matchedPerformance = visiblePerformanceRows.find((item) => item.name === row.name);

    if (!matchedPerformance) {
      return accumulator;
    }

    if (row.allocationDelta < 0 && matchedPerformance.finalScore < 1.0) {
      accumulator.push({
        name: row.name,
        message: `工时分配不足，且${appliedQuarter}最终绩效低于 1.0，需要优先关注。`,
      });
      return accumulator;
    }

    if (row.completionDelta < 0 && matchedPerformance.finalScore < 1.0) {
      accumulator.push({
        name: row.name,
        message: `任务完成进度偏慢，且${appliedQuarter}最终绩效低于 1.0，建议跟进完成节奏。`,
      });
      return accumulator;
    }

    if (row.allocationDelta >= 0 && matchedPerformance.finalScore < 1.0) {
      accumulator.push({
        name: row.name,
        message: `工时分配充足，但${appliedQuarter}最终绩效仍低于 1.0，建议复盘任务质量和产出。`,
      });
      return accumulator;
    }

    if (row.allocationDelta < 0 && matchedPerformance.finalScore >= 1.0) {
      accumulator.push({
        name: row.name,
        message: '工时略紧但绩效仍达标，可关注后续负载是否持续偏高。',
      });
    }

    return accumulator;
  }, []).slice(0, 4), [appliedQuarter, visibleHourRows, visiblePerformanceRows]);
  const quickLinks = buildQuickLinks(teamName);
  const expectedConfig = expectedView === 'current'
    ? {
        label: '本季度至今天预期有效工时',
        description: '当前筛选成员本季度截至今天的预期有效工时',
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
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">组别：{teamName}</div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">最后同步：{formatDateTime(lastUpdatedAt)}</div>
          </div>
        )}
      />

      <Card className="p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-lg font-semibold">筛选条件</div>
            <div className="mt-1 text-sm text-slate-500">先筛成员，再分别查看团队工时情况和绩效情况。</div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {quickLinks.map((item) => (
              <Link
                key={item.label}
                to={item.to}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  item.active ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">工时情况</div>
          <div className="mt-1 text-sm text-slate-500">聚合展示成员工时情况，并直接标记工时分配不足和完成情况不足的成员。</div>
        </div>
        <div className="border-b border-slate-200 bg-white px-5 py-4">
          <div className="grid gap-3">
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_240px_auto]">
              <select
                value={hoursMemberFilter}
                onChange={(event) => setHoursMemberFilter(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
              >
                {memberOptions.map((member) => (
                  <option key={member} value={member}>{member === '全部' ? '全部成员' : member}</option>
                ))}
              </select>
              <select
                value={expectedView}
                onChange={(event) => setExpectedView(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
              >
                <option value="quarter">本季度预期有效工时</option>
                <option value="current">本季度至今天预期有效工时</option>
              </select>
              <div className="flex items-center justify-end text-sm text-slate-500">
                当前成员
                {' '}
                <span className="ml-1 font-semibold text-slate-900">{visibleHourRows.length}</span>
                {' '}
                人
              </div>
            </div>
            <div className="grid gap-3 xl:grid-cols-[220px_180px_180px]">
              <select
                value={hoursAbnormalFilter}
                onChange={(event) => setHoursAbnormalFilter(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
              >
                <option value="全部成员">全部成员</option>
                <option value="只看异常成员">只看异常成员</option>
                <option value="只看分配不足">只看分配不足</option>
                <option value="只看完成不足">只看完成不足</option>
              </select>
            <select
              value={allocationSort}
              onChange={(event) => {
                setAllocationSort(event.target.value);
                if (event.target.value !== 'none') {
                  setCompletionSort('none');
                }
              }}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
                <option value="none">分配差值默认</option>
                <option value="asc">分配差值升序</option>
                <option value="desc">分配差值降序</option>
              </select>
            <select
              value={completionSort}
              onChange={(event) => {
                setCompletionSort(event.target.value);
                if (event.target.value !== 'none') {
                  setAllocationSort('none');
                }
              }}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none"
            >
                <option value="none">完成差值默认</option>
                <option value="asc">完成差值升序</option>
                <option value="desc">完成差值降序</option>
              </select>
            </div>
          </div>
        </div>
        <div className="grid gap-5 border-b border-slate-200 bg-slate-50 px-5 py-5 md:grid-cols-2 xl:grid-cols-4">
          <Card className="p-5">
            <div className="text-sm text-slate-500">当前成员数</div>
            <div className="mt-2 text-3xl font-semibold text-slate-900">{teamHoursStats.memberCount}</div>
            <div className="mt-2 text-sm text-slate-500">团队当前筛选范围内的成员数量</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">{expectedConfig.label}</div>
            <div className="mt-2 text-3xl font-semibold text-slate-900">{formatDays(expectedConfig.summaryValue)}天</div>
            <div className="mt-2 text-sm text-slate-500">{expectedConfig.description}</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">任务分配差值</div>
            <div className={`mt-2 text-3xl font-semibold ${teamHoursSummary.allocationDelta >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {teamHoursSummary.allocationDelta > 0 ? '+' : ''}
              {formatDays(teamHoursSummary.allocationDelta)}天
            </div>
            <div className="mt-2 text-sm text-slate-500">当前已排总有效工时与季度逾期总有效工时合计减去{expectedConfig.label}，正值表示分配充足。</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-slate-500">任务完成差值</div>
            <div className={`mt-2 text-3xl font-semibold ${teamHoursSummary.completionDelta >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {teamHoursSummary.completionDelta > 0 ? '+' : ''}
              {formatDays(teamHoursSummary.completionDelta)}天
            </div>
            <div className="mt-2 text-sm text-slate-500">当前已完成有效工时与季度逾期完成工时合计减去{expectedConfig.label}，正值表示完成充足。</div>
          </Card>
        </div>
        <div className="grid gap-4 border-b border-slate-200 bg-white px-5 py-4 md:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="text-xs text-slate-500">团队总工时</div>
            <div className="mt-2 text-lg font-semibold text-slate-900">{formatDays(teamHoursStats.totalHours)}天</div>
          </div>
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
                  <td className="px-5 py-4 font-medium text-slate-900">{row.name}</td>
                  <td className="px-5 py-4 text-slate-600">{row.role}</td>
                  <td className="px-5 py-4 text-slate-600">{formatDays(row[expectedConfig.rowValue])}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatDays(row.scheduledHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatDays(row.completedHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatDays(row.overdueEffectiveHours)}天</td>
                  <td className="px-5 py-4 text-slate-600">{formatDays(row.overdueCompletedHours)}天</td>
                  <td className="px-5 py-4">
                    <div className={`flex items-center gap-2 font-medium ${row.allocationInsufficient ? 'text-rose-700' : 'text-emerald-700'}`}>
                      <span>{row.allocationDelta > 0 ? '+' : ''}{formatDays(row.allocationDelta)}天</span>
                      <span className={`rounded-full px-2 py-1 text-xs ${getRiskTagClass(row.allocationRiskLevel)}`}>{row.allocationRiskLevel}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <div className={`flex items-center gap-2 font-medium ${row.completionInsufficient ? 'text-rose-700' : 'text-emerald-700'}`}>
                      <span>{row.completionDelta > 0 ? '+' : ''}{formatDays(row.completionDelta)}天</span>
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
              className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              查询季度
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

      <Card className="p-6">
        <div className="text-lg font-semibold">交叉判断</div>
        <div className="mt-1 text-sm text-slate-500">把工时差值和当前季度绩效放到一起看，帮助主管快速定位优先关注对象。</div>
        <div className="mt-4 space-y-3">
          {combinedInsights.length ? combinedInsights.map((item) => (
            <div key={`${item.name}-${item.message}`} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <div>
                <span className="font-medium text-slate-900">{item.name}</span>
                {'：'}
                {item.message}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Link
                  to={`${ROUTE_PATHS.PERSONAL_HOURS}?target=${encodeURIComponent(item.name)}`}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  查看工时管理
                </Link>
                <Link
                  to={`${ROUTE_PATHS.PERFORMANCE}?target=${encodeURIComponent(item.name)}`}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  查看绩效管理
                </Link>
              </div>
            </div>
          )) : (
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              当前筛选口径下暂无需要额外提示的交叉风险。
            </div>
          )}
        </div>
      </Card>
    </ManagerLayout>
  );
}
