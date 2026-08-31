import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchIntegrationTeamDetail } from '../api/dashboard';
import { integrationTeam } from '../mock/platformData';

export default function IntegrationTeamDetail() {
  return (
    <TeamDetailDashboard
      title="对接组"
      desc=""
      teamName="对接组"
      teamCode="INTEGRATION"
      fetcher={fetchIntegrationTeamDetail}
      fallbackRows={integrationTeam.map((item) => ({ ...item, team: '对接组' }))}
    />
  );
}
