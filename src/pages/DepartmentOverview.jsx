import { useEffect, useState } from 'react';
import { fetchDepartmentOverview } from '../api/dashboard';
import Card from '../components/Card';
import PermissionButton from '../components/PermissionButton';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import TeamTable from '../components/TeamTable';
import { BUTTON_PERMISSION_CODES } from '../constants/permissionCodes';
import ManagerLayout from '../layouts/ManagerLayout';
import { departmentStats as fallbackStats } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

export default function DepartmentOverview() {
  const user = useAuthStore((state) => state.user);
  const [stats, setStats] = useState(fallbackStats);
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let active = true;

    fetchDepartmentOverview(user).then((response) => {
      if (!active) {
        return;
      }

      setStats((prev) => ({ ...prev, ...response.data.stats }));
      setRows(response.data.rows);
    });

    return () => {
      active = false;
    };
  }, [user]);

  return (
    <ManagerLayout>
      <SectionTitle
        title="部门总览"
        desc="主管端首页，汇总部门、导航组、对接组和重点个人的关键指标。"
        right={(
          <div className="flex gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">2026 Q1</div>
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
      <div className="grid grid-cols-4 gap-5">
        <StatCard title="部门总人数" value={stats.totalMembers} sub={`导航组 ${stats.navMembers} 人，对接组 ${stats.integrationMembers} 人`} />
        <StatCard title="部门有效工时" value={`${stats.totalHours}h`} sub="较上月 +6.8%，整体负载健康" />
        <StatCard title="平均绩效" value={fallbackStats.avgPerformance} sub="研发型任务占比提升，专项交付稳定" />
        <StatCard title="AI 风险预警" value={fallbackStats.riskCount} sub="2个项目节点风险，1个人员负载偏高" />
      </div>
      <div className="grid grid-cols-3 gap-5">
        <Card className="p-5">
          <div className="text-sm text-slate-500">组织视图切换</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="rounded-2xl bg-slate-900 px-3 py-2 text-sm text-white">部门总览</span>
            <span className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-700">导航组</span>
            <span className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-700">对接组</span>
            <span className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-700">个人</span>
          </div>
          <div className="mt-5 text-sm leading-6 text-slate-500">部门总览页重点解决主管快速看全局、看风险、看资源分布的问题。</div>
        </Card>
        <Card className="col-span-2 p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-slate-500">经营观察</div>
              <div className="mt-1 text-lg font-semibold">导航组偏研发效率，对接组偏交付负载</div>
            </div>
            <PermissionButton
              code={BUTTON_PERMISSION_CODES.VIEW_AI_SUGGESTIONS}
              type="button"
              className="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
            >
              AI建议已生成
            </PermissionButton>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">导航组</div>
              <div className="mt-2 text-2xl font-semibold">610h</div>
              <div className="mt-2 text-sm text-slate-500">算法优化和复杂联调任务为主</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">对接组</div>
              <div className="mt-2 text-2xl font-semibold">771h</div>
              <div className="mt-2 text-sm text-slate-500">项目适配、现场支持、功能交付较多</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">重点个人</div>
              <div className="mt-2 text-2xl font-semibold">李四</div>
              <div className="mt-2 text-sm text-slate-500">本月156h，绩效A，高价值任务占比上升</div>
            </div>
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">部门人员明细</div>
          <div className="mt-1 text-sm text-slate-500">用于查看个人工时、绩效、风险、任务重心，支持继续下钻到个人详情页。</div>
        </div>
        <TeamTable rows={rows} showTeam />
      </Card>
    </ManagerLayout>
  );
}
