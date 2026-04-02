import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchIntegrationTeamDetail } from '../api/dashboard';
import { integrationTeam } from '../mock/platformData';

export default function IntegrationTeamDetail() {
  return (
    <TeamDetailDashboard
      title="对接组"
      desc="聚合对接组成员的工时管理和绩效管理数据，先看团队汇总，再看成员明细。"
      teamName="对接组"
      fetcher={fetchIntegrationTeamDetail}
      fallbackRows={integrationTeam.map((item) => ({ ...item, team: '对接组' }))}
    />
  );
}
