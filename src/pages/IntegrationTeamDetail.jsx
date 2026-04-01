import { useEffect, useState } from 'react';
import { fetchIntegrationTeamDetail } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import TeamTable from '../components/TeamTable';
import ManagerLayout from '../layouts/ManagerLayout';
import { integrationTeam as fallbackRows } from '../mock/platformData';
import { useAuthStore } from '../store/authStore';

export default function IntegrationTeamDetail() {
  const user = useAuthStore((state) => state.user);
  const [rows, setRows] = useState(fallbackRows);

  useEffect(() => {
    let active = true;

    fetchIntegrationTeamDetail(user).then((response) => {
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
        title="对接组详情"
        desc="重点呈现项目交付、现场支持、需求适配和模块联调工作负载。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">组别：对接组</div>}
      />
      <div className="grid grid-cols-4 gap-5">
        <StatCard title="组人数" value="5" sub="偏项目对接和模块交付方向" />
        <StatCard title="组有效工时" value="771h" sub="部门占比 55.8%" />
        <StatCard title="平均绩效" value="B+/A-" sub="任务分布较广，波动略大" />
        <StatCard title="风险提示" value="2" sub="交付期临近，现场支持压力上升" />
      </div>
      <div className="grid grid-cols-3 gap-5">
        <Card className="p-5">
          <div className="text-sm text-slate-500">任务构成</div>
          <div className="mt-4 space-y-3 text-sm text-slate-700">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">项目对接：39%</div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">现场支持：34%</div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">功能交付：27%</div>
          </div>
        </Card>
        <Card className="col-span-2 p-5">
          <div className="text-sm text-slate-500">主管建议</div>
          <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-amber-900">建议将常见问题处理流程标准化，减少重复性支持工作对骨干成员的消耗。</div>
            <div className="rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sky-900">适合建立项目问题知识库与版本适配清单，提升交付人效和稳定性。</div>
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">对接组成员明细</div>
        </div>
        <TeamTable rows={rows} />
      </Card>
    </ManagerLayout>
  );
}
