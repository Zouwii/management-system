import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchNavTeamDetail } from '../api/dashboard';
import { navTeam } from '../mock/platformData';

export default function NavTeamDetail() {
  return (
    <TeamDetailDashboard
      title="导航组"
      desc="聚合导航组成员的工时管理和绩效管理数据，先看团队汇总，再看成员明细。"
      teamName="导航组"
      fetcher={fetchNavTeamDetail}
      fallbackRows={navTeam.map((item) => ({ ...item, team: '导航组' }))}
    />
  );
}
