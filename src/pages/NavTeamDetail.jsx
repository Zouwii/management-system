import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchNavTeamDetail } from '../api/dashboard';
import { navTeam } from '../mock/platformData';

export default function NavTeamDetail() {
  return (
    <TeamDetailDashboard
      title="导航组详情"
      desc="重点呈现导航算法、控制优化、联调任务和成员负载分布。"
      teamName="导航组"
      fetcher={fetchNavTeamDetail}
      fallbackRows={navTeam.map((item) => ({ ...item, team: '导航组' }))}
      composition={[
        { label: '算法优化', percent: '46%', note: '路径规划、避障与复杂场景性能优化。', barClass: 'bg-sky-500' },
        { label: '联调验证', percent: '31%', note: '跨模块联调、路测复现与版本回归。', barClass: 'bg-emerald-500' },
        { label: '复盘沉淀', percent: '23%', note: '日志复盘、方案总结与技术标准化输出。', barClass: 'bg-amber-500' },
      ]}
      suggestions={[
        {
          title: '研发连续性',
          content: '建议减少核心成员在碎片化排查任务上的时间占用，保障算法研发连续性。',
          className: 'border-amber-100 bg-amber-50 text-amber-900',
        },
        {
          title: '专题沉淀',
          content: '适合将控制器优化、路径规划实验、数据复盘形成标准化专题输出。',
          className: 'border-emerald-100 bg-emerald-50 text-emerald-900',
        },
      ]}
    />
  );
}
