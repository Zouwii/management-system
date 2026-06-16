import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchNavTeamDetail } from '../api/dashboard';
import { navTeam } from '../mock/platformData';

export default function NavTeamDetail() {
  return (
    <TeamDetailDashboard
      title="导航组"
      desc=""
      teamName="导航组"
      teamKey="nav"
      fetcher={fetchNavTeamDetail}
      fallbackRows={navTeam.map((item) => ({ ...item, team: '导航组' }))}
    />
  );
}
