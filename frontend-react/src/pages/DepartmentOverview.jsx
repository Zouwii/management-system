import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchDepartmentOverview } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import { ROUTE_PATHS } from '../constants/routes';
import ManagerLayout from '../layouts/ManagerLayout';
import { departmentStats as fallbackStats } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';
import { formatDateTime } from '../utils/workHours';

function getQuarterLabel(year, quarter) {
  return `${year} Q${quarter}`;
}

// ── 基于真实 API 数据的计算函数 ──

function buildMemberHoursRows(rows) {
  return rows.map((row) => {
    const expected = row.expectedEffectiveHours || 0;
    const scheduled = row.scheduledHours || 0;
    const completed = row.completedHours || 0;
    const overdue = row.overdueHours || 0;
    const overdueCompleted = row.overdueCompletedHours || 0;
    const allocationDelta = scheduled + overdue - expected;
    const completionDelta = completed + overdueCompleted - expected;
    return {
      name: row.userName,
      allocationDelta,
      completionDelta,
      highRisk: allocationDelta < 0 || completionDelta < 0,
    };
  });
}

function buildMemberPerfRows(rows) {
  return rows.map((row) => ({
    name: row.userName,
    finalScore: row.finalScore ?? 0,
  }));
}

function buildTeamMonitor(rows) {
  const totalMembers = rows.length;
  const totalHours = rows.reduce((sum, r) => {
    return sum + (r.scheduledHours || 0) + (r.overdueHours || 0) + (r.costHour || 0) + (r.issueCostHour || 0);
  }, 0);
  const perfRows = buildMemberPerfRows(rows);
  const hourRows = buildMemberHoursRows(rows);
  const validPerf = perfRows.filter((r) => r.finalScore > 0);
  const avgFinalPerformance = validPerf.length
    ? (validPerf.reduce((s, r) => s + r.finalScore, 0) / validPerf.length).toFixed(2)
    : '0.00';
  return {
    totalMembers,
    totalHours,
    avgFinalPerformance,
    allocationRiskCount: hourRows.filter((r) => r.allocationDelta < 0).length,
    completionRiskCount: hourRows.filter((r) => r.completionDelta < 0).length,
    highRiskCount: hourRows.filter((r) => r.highRisk).length,
    lowPerformanceCount: perfRows.filter((r) => r.finalScore > 0 && r.finalScore < 1.0).length,
    allocationDelta: hourRows.reduce((s, r) => s + r.allocationDelta, 0),
    completionDelta: hourRows.reduce((s, r) => s + r.completionDelta, 0),
  };
}

export default function DepartmentOverview() {
  const user = useAuthStore((state) => state.user);
  const [stats, setStats] = useState(fallbackStats);
  const [rows, setRows] = useState([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [apiQuarter, setApiQuarter] = useState(null);
  const [apiPerfQuarter, setApiPerfQuarter] = useState(null);

  useEffect(() => {
    let active = true;

    fetchDepartmentOverview(user).then((response) => {
      if (!active) return;
      const data = response?.data ?? {};
      const apiStats = data.stats ?? {};
      setStats((prev) => ({
        ...prev,
        totalMembers: apiStats.totalMembers ?? prev.totalMembers,
        navMembers: apiStats.navMembers ?? prev.navMembers,
        integrationMembers: apiStats.servoMembers ?? prev.integrationMembers,
        totalHours: apiStats.totalHours ?? prev.totalHours,
      }));
      setRows(data.rows ?? []);
      setLastUpdatedAt(data.lastUpdatedAt || new Date().toISOString());
      setApiQuarter(data.quarter ?? null);
      setApiPerfQuarter(data.perfQuarter ?? null);
    }).catch(() => {});

    return () => { active = false; };
  }, [user]);

  const quarterLabel = apiQuarter
    ? getQuarterLabel(apiQuarter.year, apiQuarter.quarter)
    : fallbackStats.quarter ?? '2026 Q2';
  const perfQuarterLabel = apiPerfQuarter
    ? getQuarterLabel(apiPerfQuarter.year, apiPerfQuarter.quarter)
    : quarterLabel;

  const navRows = useMemo(() => rows.filter((row) => row.team === '导航组'), [rows]);
  const integrationRows = useMemo(() => rows.filter((row) => row.team === '对接组'), [rows]);
  const departmentSummary = useMemo(() => {
    const totalHours = rows.reduce((sum, r) => {
      return sum + (r.scheduledHours || 0) + (r.overdueHours || 0) + (r.costHour || 0) + (r.issueCostHour || 0);
    }, 0);
    return { totalHours, totalMembers: rows.length };
  }, [rows]);
  const navMonitor = useMemo(() => buildTeamMonitor(navRows), [navRows]);
  const integrationMonitor = useMemo(() => buildTeamMonitor(integrationRows), [integrationRows]);

  const departmentPerfRows = useMemo(() => buildMemberPerfRows(rows), [rows]);
  const departmentHoursRows = useMemo(() => buildMemberHoursRows(rows), [rows]);
  const departmentAlerts = useMemo(() => ({
    allocationRiskCount: departmentHoursRows.filter((row) => row.allocationDelta < 0).length,
    completionRiskCount: departmentHoursRows.filter((row) => row.completionDelta < 0).length,
    lowPerformanceCount: departmentPerfRows.filter((row) => row.finalScore > 0 && row.finalScore < 1.0).length,
  }), [departmentHoursRows, departmentPerfRows]);
  const rankingCards = useMemo(() => {
    const teamItems = [
      { label: '导航组', route: ROUTE_PATHS.NAV_TEAM_DETAIL, ...navMonitor },
      { label: '对接组', route: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL, ...integrationMonitor },
    ];

    const topHours = [...teamItems].sort((left, right) => right.totalHours - left.totalHours)[0];
    const topPerformance = [...teamItems].sort((left, right) => Number(right.avgFinalPerformance) - Number(left.avgFinalPerformance))[0];
    const topRisk = [...teamItems].sort((left, right) => (right.highRiskCount + right.lowPerformanceCount) - (left.highRiskCount + left.lowPerformanceCount))[0];

    return [
      {
        title: '工时排名',
        value: `${topHours?.label ?? '-'} · ${(topHours?.totalHours ?? 0).toFixed(1)}`,
        to: topHours?.route ?? ROUTE_PATHS.DEPARTMENT_OVERVIEW,
      },
      {
        title: '绩效排名',
        value: `${topPerformance?.label ?? '-'} · ${topPerformance?.avgFinalPerformance ?? '0.00'}`,
        to: topPerformance?.route ?? ROUTE_PATHS.DEPARTMENT_OVERVIEW,
      },
      {
        title: '异常优先级',
        value: `${topRisk?.label ?? '-'} · ${(topRisk?.highRiskCount ?? 0) + (topRisk?.lowPerformanceCount ?? 0)}项`,
        to: `${topRisk?.route ?? ROUTE_PATHS.DEPARTMENT_OVERVIEW}?hoursAbnormal=abnormal&performanceScore=below`,
      },
    ];
  }, [integrationMonitor, navMonitor]);
  const departmentInsights = useMemo(() => {
    const insights = [];

    if (navMonitor.allocationDelta < integrationMonitor.allocationDelta) {
      insights.push(`导航组的任务分配差值更低，当前更需要关注工时分配。`);
    } else if (integrationMonitor.allocationDelta < navMonitor.allocationDelta) {
      insights.push(`对接组的任务分配差值更低，当前更需要关注工时分配。`);
    }

    if (navMonitor.completionDelta < integrationMonitor.completionDelta) {
      insights.push(`导航组的任务完成差值更低，当前更需要关注完成进度。`);
    } else if (integrationMonitor.completionDelta < navMonitor.completionDelta) {
      insights.push(`对接组的任务完成差值更低，当前更需要关注完成进度。`);
    }

    if (navMonitor.lowPerformanceCount > 0 && navMonitor.allocationRiskCount > 0) {
      insights.push(`导航组存在工时不足且绩效低于 1.0 的成员，建议优先下钻查看。`);
    }

    if (integrationMonitor.lowPerformanceCount > 0 && integrationMonitor.allocationRiskCount > 0) {
      insights.push(`对接组存在工时不足且绩效低于 1.0 的成员，建议优先下钻查看。`);
    }

    if (navMonitor.lowPerformanceCount > 0 && navMonitor.allocationRiskCount === 0) {
      insights.push(`导航组工时分配基本充足，但仍有低绩效成员，建议复盘任务质量。`);
    }

    if (integrationMonitor.lowPerformanceCount > 0 && integrationMonitor.allocationRiskCount === 0) {
      insights.push(`对接组工时分配基本充足，但仍有低绩效成员，建议复盘任务质量。`);
    }

    return insights.slice(0, 4);
  }, [integrationMonitor, navMonitor]);

  function renderTeamCard(title, monitor, route) {
    return (
      <Card className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">{title}</div>
            <div className="mt-1 text-sm text-slate-500">聚合该团队成员的工时和绩效结果，可直接下钻查看异常。</div>
          </div>
          <Link
            to={route}
            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            查看团队页
          </Link>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">成员数</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900">{monitor.totalMembers}</div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">总工时</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900">{(monitor.totalHours ?? 0).toFixed(1)}</div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">平均最终绩效</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900">{monitor.avgFinalPerformance}</div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link to={`${route}?hoursAbnormal=allocation`} className="rounded-full border border-rose-100 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">
            分配不足 {monitor.allocationRiskCount} 人
          </Link>
          <Link to={`${route}?hoursAbnormal=completion`} className="rounded-full border border-amber-100 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
            完成不足 {monitor.completionRiskCount} 人
          </Link>
          <Link to={`${route}?performanceScore=below`} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700">
            绩效低于 1.0 {monitor.lowPerformanceCount} 人
          </Link>
        </div>
      </Card>
    );
  }

  return (
    <ManagerLayout>
      <SectionTitle
        title="部门总览"
        right={(
          <div className="flex flex-wrap justify-end gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">{quarterLabel}</div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">部门：本体开发部</div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">最后同步：{lastUpdatedAt ? formatDateTime(lastUpdatedAt) : '暂无'}</div>
          </div>
        )}
      />

      <Card className="p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-lg font-semibold">聚合视图</div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Link to={ROUTE_PATHS.DEPARTMENT_OVERVIEW} className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white">部门总览</Link>
            <Link to={ROUTE_PATHS.NAV_TEAM_DETAIL} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">导航组</Link>
            <Link to={ROUTE_PATHS.INTEGRATION_TEAM_DETAIL} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">对接组</Link>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-3">
        <StatCard title="部门总人数" value={rows.length || stats.totalMembers} sub={`导航组 ${stats.navMembers} 人，对接组 ${stats.integrationMembers} 人`} />
        <StatCard title="部门总工时" value={`${(departmentSummary.totalHours || stats.totalHours || 0).toFixed(1)}`} sub="聚合导航组和对接组全部成员工时" />
        <StatCard title="平均最终绩效" value={departmentPerfRows.filter(r => r.finalScore > 0).length ? (departmentPerfRows.filter(r => r.finalScore > 0).reduce((s, r) => s + r.finalScore, 0) / departmentPerfRows.filter(r => r.finalScore > 0).length).toFixed(2) : '0.00'} sub={`${perfQuarterLabel} 部门平均最终绩效`} />
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <Card className="border border-rose-100 bg-rose-50 p-5 text-rose-800">
          <div className="text-sm">分配不足人数</div>
          <div className="mt-2 text-3xl font-semibold">{departmentAlerts.allocationRiskCount}</div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Link to={`${ROUTE_PATHS.NAV_TEAM_DETAIL}?hoursAbnormal=allocation`} className="rounded-full border border-rose-200 bg-white px-3 py-1.5 font-medium text-rose-700">
              导航组 {navMonitor.allocationRiskCount} 人
            </Link>
            <Link to={`${ROUTE_PATHS.INTEGRATION_TEAM_DETAIL}?hoursAbnormal=allocation`} className="rounded-full border border-rose-200 bg-white px-3 py-1.5 font-medium text-rose-700">
              对接组 {integrationMonitor.allocationRiskCount} 人
            </Link>
          </div>
        </Card>
        <Card className="border border-amber-100 bg-amber-50 p-5 text-amber-800">
          <div className="text-sm">完成不足人数</div>
          <div className="mt-2 text-3xl font-semibold">{departmentAlerts.completionRiskCount}</div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Link to={`${ROUTE_PATHS.NAV_TEAM_DETAIL}?hoursAbnormal=completion`} className="rounded-full border border-amber-200 bg-white px-3 py-1.5 font-medium text-amber-700">
              导航组 {navMonitor.completionRiskCount} 人
            </Link>
            <Link to={`${ROUTE_PATHS.INTEGRATION_TEAM_DETAIL}?hoursAbnormal=completion`} className="rounded-full border border-amber-200 bg-white px-3 py-1.5 font-medium text-amber-700">
              对接组 {integrationMonitor.completionRiskCount} 人
            </Link>
          </div>
        </Card>
        <Card className="border border-slate-200 bg-slate-50 p-5 text-slate-800">
          <div className="text-sm">绩效低于 1.0 人数</div>
          <div className="mt-2 text-3xl font-semibold">{departmentAlerts.lowPerformanceCount}</div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Link to={`${ROUTE_PATHS.NAV_TEAM_DETAIL}?performanceScore=below`} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700">
              导航组 {navMonitor.lowPerformanceCount} 人
            </Link>
            <Link to={`${ROUTE_PATHS.INTEGRATION_TEAM_DETAIL}?performanceScore=below`} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700">
              对接组 {integrationMonitor.lowPerformanceCount} 人
            </Link>
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        {renderTeamCard('导航组', navMonitor, ROUTE_PATHS.NAV_TEAM_DETAIL)}
        {renderTeamCard('对接组', integrationMonitor, ROUTE_PATHS.INTEGRATION_TEAM_DETAIL)}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card className="p-6">
          <div className="text-lg font-semibold">团队排序</div>
          <div className="mt-1 text-sm text-slate-500">按工时、绩效和异常优先级快速判断当前更需要下钻哪个团队。</div>
          <div className="mt-5 space-y-3">
            {rankingCards.map((item) => (
              <Link key={item.title} to={item.to} className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700 hover:bg-slate-100">
                <span className="font-medium text-slate-900">{item.title}</span>
                <span>{item.value}</span>
              </Link>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-lg font-semibold">部门提醒</div>
          <div className="mt-1 text-sm text-slate-500">基于团队工时差值和季度绩效做轻量判断，帮助部门主管快速定位异常方向。</div>
          <div className="mt-5 space-y-3">
            {departmentInsights.length ? departmentInsights.map((item) => (
              <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {item}
              </div>
            )) : (
              <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                当前部门口径下暂无需要额外提示的团队风险。
              </div>
            )}
          </div>
        </Card>
      </div>
    </ManagerLayout>
  );
}
