import { Link } from 'react-router-dom';
import { ROUTE_PATHS } from '../constants/routes';
import DepartmentOverview from './DepartmentOverview';
import NavTeamDetail from './NavTeamDetail';
import IntegrationTeamDetail from './IntegrationTeamDetail';
import PersonalHours from './PersonalHours';
import PerformancePage from './PerformancePage';
import AIAnalysisPage from './AIAnalysisPage';

const overviewPages = [
  { label: '部门总览页', to: ROUTE_PATHS.DEPARTMENT_OVERVIEW },
  { label: '导航组详情页', to: ROUTE_PATHS.NAV_TEAM_DETAIL },
  { label: '对接组详情页', to: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL },
  { label: '个人工时页', to: ROUTE_PATHS.PERSONAL_HOURS },
  { label: '绩效页', to: ROUTE_PATHS.PERFORMANCE },
  { label: 'AI分析页', to: ROUTE_PATHS.AI_ANALYSIS },
  { label: '登录页', to: ROUTE_PATHS.LOGIN },
];

export default function Prototype() {
  return (
    <div className="min-h-screen bg-slate-100 p-6 text-slate-900">
      <div className="mx-auto max-w-7xl space-y-12">
        <div>
          <div className="text-3xl font-semibold">本体开发部数据管理平台｜完整展开版</div>
          <div className="mt-2 text-slate-500">已展开部门总览页、导航组详情页、对接组详情页、个人工时页、绩效页和 AI 分析页。</div>
          <div className="mt-5 flex flex-wrap gap-2">
            {overviewPages.map((page) => (
              <Link
                key={page.to}
                to={page.to}
                className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              >
                {page.label}
              </Link>
            ))}
          </div>
        </div>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">01｜主管端 · 部门总览页</div>
          <DepartmentOverview />
        </section>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">02｜主管端 · 导航组详情页</div>
          <NavTeamDetail />
        </section>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">03｜主管端 · 对接组详情页</div>
          <IntegrationTeamDetail />
        </section>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">04｜员工端 · 个人工时页</div>
          <PersonalHours />
        </section>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">05｜员工端 · 绩效页</div>
          <PerformancePage />
        </section>

        <section className="space-y-4">
          <div className="text-sm font-semibold text-slate-500">06｜员工端 · AI分析页</div>
          <AIAnalysisPage />
        </section>

      </div>
    </div>
  );
}
