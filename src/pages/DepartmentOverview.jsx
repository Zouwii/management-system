import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchDepartmentOverview } from '../api/dashboard';
import Card from '../components/Card';
import PermissionButton from '../components/PermissionButton';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import TeamTable from '../components/TeamTable';
import { BUTTON_PERMISSION_CODES } from '../constants/permissionCodes';
import { ROUTE_PATHS } from '../constants/routes';
import ManagerLayout from '../layouts/ManagerLayout';
import { departmentStats as fallbackStats } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';
import {
  buildDepartmentDistribution,
  buildRiskRows,
  buildTeamSummary,
  getCurrentLocalDateTime,
  parseRate,
} from '../utils/managerDashboard';
import { formatDateTime, formatDays } from '../utils/workHours';

function getQuarterLabel() {
  const now = new Date();
  const quarter = Math.floor(now.getMonth() / 3) + 1;
  return `${now.getFullYear()} Q${quarter}`;
}

export default function DepartmentOverview() {
  const user = useAuthStore((state) => state.user);
  const [stats, setStats] = useState(fallbackStats);
  const [rows, setRows] = useState([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(getCurrentLocalDateTime());
  const [teamFilter, setTeamFilter] = useState('全部');
  const [riskFilter, setRiskFilter] = useState('全部');

  useEffect(() => {
    let active = true;

    fetchDepartmentOverview(user).then((response) => {
      if (!active) {
        return;
      }

      setStats((prev) => ({ ...prev, ...response.data.stats }));
      setRows(response.data.rows ?? []);
      setLastUpdatedAt(getCurrentLocalDateTime());
    });

    return () => {
      active = false;
    };
  }, [user]);

  const filteredRows = useMemo(() => rows
    .filter((row) => teamFilter === '全部' || row.team === teamFilter)
    .filter((row) => riskFilter === '全部' || row.risk === riskFilter), [riskFilter, rows, teamFilter]);
  const summary = useMemo(() => buildTeamSummary(filteredRows), [filteredRows]);
  const distribution = useMemo(() => buildDepartmentDistribution(filteredRows), [filteredRows]);
  const riskRows = useMemo(() => buildRiskRows(filteredRows).slice(0, 4), [filteredRows]);
  const highestRate = useMemo(() => {
    const sortedRows = [...filteredRows].sort((left, right) => parseRate(right.effectiveRate) - parseRate(left.effectiveRate));
    return sortedRows[0];
  }, [filteredRows]);

  return (
    <ManagerLayout>
      <SectionTitle
        title="部门总览"
        desc="主管端首页，汇总部门、导航组、对接组和重点个人的关键指标。"
        right={(
          <div className="flex flex-wrap justify-end gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">{getQuarterLabel()}</div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">部门：本体开发部</div>
            <PermissionButton
              code={BUTTON_PERMISSION_CODES.EXPORT_REPORT}
              type="button"
              className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700"
            >
              导出报表
            </PermissionButton>
          </div>
        )}
      />

      <Card className="p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="text-lg font-semibold">组织视图控制</div>
            <div className="mt-1 text-sm text-slate-500">按照个人工时页的节奏，先切范围，再看组织结构、风险和人员明细。</div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Link to={ROUTE_PATHS.DEPARTMENT_OVERVIEW} className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white">部门总览</Link>
            <Link to={ROUTE_PATHS.NAV_TEAM_DETAIL} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">导航组</Link>
            <Link to={ROUTE_PATHS.INTEGRATION_TEAM_DETAIL} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">对接组</Link>
            <Link to={ROUTE_PATHS.PERSONAL_HOURS} className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">个人工时</Link>
          </div>
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">团队范围</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {['全部', '导航组', '对接组'].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setTeamFilter(item)}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${teamFilter === item ? 'bg-slate-900 text-white' : 'border border-slate-200 bg-white text-slate-700'}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm text-slate-500">风险范围</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {['全部', '低', '中'].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setRiskFilter(item)}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${riskFilter === item ? 'bg-amber-500 text-white' : 'border border-slate-200 bg-white text-slate-700'}`}
                >
                  {item === '全部' ? '全部风险' : `${item}风险`}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
            最后同步：
            {' '}
            <span className="font-medium text-slate-900">{formatDateTime(lastUpdatedAt)}</span>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-4">
        <StatCard title="部门总人数" value={filteredRows.length || stats.totalMembers} sub={`导航组 ${stats.navMembers} 人，对接组 ${stats.integrationMembers} 人`} />
        <StatCard title="部门有效工天" value={`${formatDays(summary.totalHours || stats.totalHours)}天`} sub={`平均效率 ${summary.avgEffectiveRate}`} />
        <StatCard title="平均绩效" value={summary.avgPerformance} sub={highestRate ? `${highestRate.name} 有效率最高 ${highestRate.effectiveRate}` : '暂无成员数据'} />
        <StatCard title="AI 风险预警" value={riskRows.length} sub={riskRows.length ? `${riskRows[0].name} 等成员负载需关注` : '当前暂无重点风险'} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">组织负载分布</div>
              <div className="mt-1 text-sm text-slate-500">从部门口径直接拆到团队，先看哪一侧更重，再决定是否下钻。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">单位：工时占比</div>
          </div>
          <div className="mt-5 space-y-4">
            {distribution.map((item) => (
              <div key={item.team} className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-slate-900">{item.team}</div>
                    <div className="mt-1 text-sm text-slate-500">{formatDays(item.hours)}天</div>
                  </div>
                  <div className="text-lg font-semibold text-slate-900">{item.ratio}%</div>
                </div>
                <div className="mt-3 h-3 rounded-full bg-white">
                  <div className={`h-3 rounded-full ${item.team === '导航组' ? 'bg-sky-500' : 'bg-emerald-500'}`} style={{ width: `${item.ratio}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">经营观察</div>
              <div className="mt-1 text-sm text-slate-500">保留业务判断，但把信息拆成更容易扫描的观察卡片。</div>
            </div>
            <PermissionButton
              code={BUTTON_PERMISSION_CODES.VIEW_AI_SUGGESTIONS}
              type="button"
              className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
            >
              AI建议已生成
            </PermissionButton>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">导航组</div>
              <div className="mt-2 text-2xl font-semibold">{formatDays(distribution.find((item) => item.team === '导航组')?.hours ?? 0)}天</div>
              <div className="mt-2 text-sm text-slate-500">偏研发效率，适合继续承接算法优化和复杂联调。</div>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">对接组</div>
              <div className="mt-2 text-2xl font-semibold">{formatDays(distribution.find((item) => item.team === '对接组')?.hours ?? 0)}天</div>
              <div className="mt-2 text-sm text-slate-500">偏交付负载，建议通过问题库和清单化来压缩重复支持。</div>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">重点个人</div>
              <div className="mt-2 text-2xl font-semibold">{summary.topMember?.name ?? '暂无'}</div>
              <div className="mt-2 text-sm text-slate-500">
                {summary.topMember ? `本期 ${formatDays(summary.topMember.hours)}天，绩效 ${summary.topMember.perf}，聚焦 ${summary.topMember.focus}` : '暂无可推荐成员'}
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <Card className="p-6">
          <div className="text-lg font-semibold">风险观察</div>
          <div className="mt-1 text-sm text-slate-500">把中风险成员前置展示，主管无需先翻表格再判断。</div>
          <div className="mt-5 space-y-3">
            {riskRows.length ? riskRows.map((row) => (
              <div key={row.name} className="rounded-3xl border border-amber-100 bg-amber-50 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-slate-900">{row.name}</div>
                    <div className="mt-1 text-sm text-slate-600">{row.team} · {row.focus}</div>
                  </div>
                  <div className="text-right text-sm text-amber-900">
                    <div>{formatDays(row.hours)}天</div>
                    <div>{row.effectiveRate}</div>
                  </div>
                </div>
              </div>
            )) : (
              <div className="rounded-3xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-800">当前筛选口径下暂无重点风险成员。</div>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-lg font-semibold">管理动作建议</div>
          <div className="mt-1 text-sm text-slate-500">把原本分散在说明文案里的动作，整理成主管可执行清单。</div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-sky-100 bg-sky-50 p-4 text-sm text-sky-900">
              <div className="font-medium">负载再平衡</div>
              <div className="mt-2 leading-6">导航组适合继续承担深度研发，对接组需要通过标准化资料减少重复项目支持。</div>
            </div>
            <div className="rounded-3xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900">
              <div className="font-medium">重点人跟踪</div>
              <div className="mt-2 leading-6">对工时持续上升且风险不低的成员建立周观察，避免高价值任务被碎片化工作挤压。</div>
            </div>
            <div className="rounded-3xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="font-medium">专项沉淀</div>
              <div className="mt-2 leading-6">导航组沉淀控制器和规划专题，对接组沉淀版本适配和问题闭环清单。</div>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
              <div className="font-medium">跨页下钻</div>
              <div className="mt-2 leading-6">通过顶部视图切换直接进入组页，再用成员表筛选查看具体人员，减少来回跳转成本。</div>
            </div>
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-lg font-semibold">部门人员明细</div>
              <div className="mt-1 text-sm text-slate-500">用于查看个人工时、绩效、风险和任务重心，支持按关键字和排序快速定位成员。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
              当前口径共
              {' '}
              <span className="font-medium text-slate-900">{filteredRows.length}</span>
              {' '}
              人
            </div>
          </div>
        </div>
        <TeamTable rows={filteredRows} showTeam />
      </Card>
    </ManagerLayout>
  );
}
