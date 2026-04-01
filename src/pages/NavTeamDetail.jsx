import { useEffect, useState } from 'react';
import { fetchNavTeamDetail } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import TeamTable from '../components/TeamTable';
import ManagerLayout from '../layouts/ManagerLayout';
import { navTeam as fallbackRows } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

export default function NavTeamDetail() {
  const user = useAuthStore((state) => state.user);
  const [rows, setRows] = useState(fallbackRows);

  useEffect(() => {
    let active = true;

    fetchNavTeamDetail(user).then((response) => {
      if (active) {
        setRows(response.data.rows);
      }
    });

    return () => {
      active = false;
    };
  }, [user]);

  return (
    <ManagerLayout>
      <SectionTitle
        title="导航组详情"
        desc="重点呈现导航算法、控制优化、联调任务和成员负载分布。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">组别：导航组</div>}
      />
      <div className="grid grid-cols-4 gap-5">
        <StatCard title="组人数" value="4" sub="核心偏算法与控制方向" />
        <StatCard title="组有效工时" value="610h" sub="部门占比 44.2%" />
        <StatCard title="平均绩效" value="A-" sub="高复杂度任务比例较高" />
        <StatCard title="风险提示" value="2" sub="1人联调偏多，1人工时波动" />
      </div>
      <div className="grid grid-cols-3 gap-5">
        <Card className="p-5">
          <div className="text-sm text-slate-500">任务构成</div>
          <div className="mt-4 space-y-3 text-sm text-slate-700">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">算法优化：46%</div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">联调验证：31%</div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">复盘沉淀：23%</div>
          </div>
        </Card>
        <Card className="col-span-2 p-5">
          <div className="text-sm text-slate-500">主管建议</div>
          <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-amber-900">建议减少核心成员在碎片化排查任务上的时间占用，保障算法研发连续性。</div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-emerald-900">适合将控制器优化、路径规划实验、数据复盘形成标准化专题输出。</div>
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">导航组成员明细</div>
        </div>
        <TeamTable rows={rows} />
      </Card>
    </ManagerLayout>
  );
}
