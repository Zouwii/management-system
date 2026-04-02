import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Card from './Card';
import SectionTitle from './SectionTitle';
import StatCard from './StatCard';
import TeamTable from './TeamTable';
import ManagerLayout from '../layouts/ManagerLayout';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import {
  buildRiskRows,
  buildTeamSummary,
  buildTeamTrend,
  getCurrentLocalDateTime,
} from '../utils/managerDashboard';
import { formatDateTime, formatDays } from '../utils/workHours';

function buildQuickLinks(teamName) {
  return [
    { label: '部门总览', to: ROUTE_PATHS.DEPARTMENT_OVERVIEW, active: false },
    { label: '导航组', to: ROUTE_PATHS.NAV_TEAM_DETAIL, active: teamName === '导航组' },
    { label: '对接组', to: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL, active: teamName === '对接组' },
    { label: '个人工时', to: ROUTE_PATHS.PERSONAL_HOURS, active: false },
  ];
}

export default function TeamDetailDashboard({
  title,
  desc,
  teamName,
  fetcher,
  fallbackRows,
  composition,
  suggestions,
}) {
  const user = useAuthStore((state) => state.user);
  const [rows, setRows] = useState(fallbackRows);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(getCurrentLocalDateTime());
  const [viewMode, setViewMode] = useState('全部成员');
  const [riskMode, setRiskMode] = useState('全部风险');

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

  const visibleRows = useMemo(() => {
    let nextRows = rows;

    if (viewMode === '高工天成员') {
      nextRows = rows.filter((row) => row.hours >= 155);
    }

    if (riskMode === '风险成员') {
      nextRows = nextRows.filter((row) => row.risk !== '低');
    }

    return nextRows;
  }, [riskMode, rows, viewMode]);

  const summary = useMemo(() => buildTeamSummary(visibleRows), [visibleRows]);
  const riskRows = useMemo(() => buildRiskRows(visibleRows).slice(0, 3), [visibleRows]);
  const trendRows = useMemo(() => buildTeamTrend(visibleRows), [visibleRows]);
  const maxTrendValue = Math.max(...trendRows.map((item) => Math.abs(item.trendHours)), 1);
  const quickLinks = buildQuickLinks(teamName);

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
            <div className="text-lg font-semibold">团队视图控制</div>
            <div className="mt-1 text-sm text-slate-500">保持和个人工时页一致的页面节奏，先切换范围，再看结构、风险和成员明细。</div>
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
        <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">成员范围</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {['全部成员', '高工天成员'].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setViewMode(item)}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${
                    viewMode === item ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white text-slate-700'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">风险视图</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {['全部风险', '风险成员'].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setRiskMode(item)}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${
                    riskMode === item ? 'bg-amber-500 text-white' : 'border border-slate-200 bg-white text-slate-700'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
            当前视图：
            {' '}
            <span className="font-medium text-slate-900">{viewMode}</span>
            {' · '}
            <span className="font-medium text-slate-900">{riskMode}</span>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-4">
        <StatCard title="组人数" value={summary.totalMembers} sub="当前筛选口径下的可见成员数" />
        <StatCard title="组有效工天" value={`${formatDays(summary.totalHours)}天`} sub={`正向波动成员 ${summary.positiveTrendCount} 人`} />
        <StatCard title="平均有效率" value={summary.avgEffectiveRate} sub={`平均绩效 ${summary.avgPerformance}`} />
        <StatCard title="风险成员" value={summary.mediumRiskCount} sub={summary.topMember ? `当前最高负载：${summary.topMember.name}` : '暂无重点风险'} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">任务构成</div>
              <div className="mt-1 text-sm text-slate-500">保留原页面的业务解读，但换成更强的结构化呈现。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">聚焦团队职责分布</div>
          </div>
          <div className="mt-5 space-y-4">
            {composition.map((item) => (
              <div key={item.label} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-slate-900">{item.label}</div>
                    <div className="mt-1 text-sm text-slate-500">{item.note}</div>
                  </div>
                  <div className="text-lg font-semibold text-slate-900">{item.percent}</div>
                </div>
                <div className="mt-3 h-3 rounded-full bg-white">
                  <div className={`h-3 rounded-full ${item.barClass}`} style={{ width: item.percent }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">成员变化趋势</div>
              <div className="mt-1 text-sm text-slate-500">用成员维度替代月份柱状图，快速看谁在抬升负载、谁在回落。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">单位：天</div>
          </div>
          <div className="mt-5 space-y-3">
            {trendRows.map((row) => (
              <div key={row.name} className="rounded-3xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-slate-900">{row.name}</div>
                    <div className="mt-1 text-sm text-slate-500">{row.focus}</div>
                  </div>
                  <div className={`text-lg font-semibold ${row.trendHours >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {row.trendHours >= 0 ? '+' : ''}
                    {formatDays(row.trendHours)}天
                  </div>
                </div>
                <div className="mt-3 h-3 rounded-full bg-slate-100">
                  <div
                    className={`h-3 rounded-full ${row.trendHours >= 0 ? 'bg-emerald-500' : 'bg-rose-400'}`}
                    style={{ width: `${Math.max((Math.abs(row.trendHours) / maxTrendValue) * 100, 8)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="p-6">
          <div className="text-lg font-semibold">风险观察</div>
          <div className="mt-1 text-sm text-slate-500">把高风险和高负载成员前置，不再埋在表格里。</div>
          <div className="mt-5 space-y-3">
            {riskRows.length ? riskRows.map((row) => (
              <div key={row.name} className="rounded-3xl border border-amber-100 bg-amber-50 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-slate-900">{row.name}</div>
                    <div className="mt-1 text-sm text-slate-600">{row.focus}</div>
                  </div>
                  <div className="text-right text-sm text-amber-900">
                    <div>{formatDays(row.hours)}天</div>
                    <div>{row.effectiveRate}</div>
                  </div>
                </div>
              </div>
            )) : (
              <div className="rounded-3xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-800">当前口径下暂无需要重点关注的风险成员。</div>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-lg font-semibold">主管建议</div>
          <div className="mt-1 text-sm text-slate-500">延续旧页面内容，但改成可快速扫描的建议卡片。</div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {suggestions.map((item) => (
              <div key={item.content} className={`rounded-3xl border p-4 text-sm ${item.className}`}>
                <div className="font-medium">{item.title}</div>
                <div className="mt-2 leading-6">{item.content}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-lg font-semibold">{teamName}成员明细</div>
              <div className="mt-1 text-sm text-slate-500">支持按风险、绩效、关键词和工天排序查看成员负载。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
              当前口径共
              {' '}
              <span className="font-medium text-slate-900">{visibleRows.length}</span>
              {' '}
              人
            </div>
          </div>
        </div>
        <TeamTable rows={visibleRows} />
      </Card>
    </ManagerLayout>
  );
}
