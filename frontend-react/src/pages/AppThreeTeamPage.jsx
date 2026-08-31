import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchAppThreeTeamDetail } from '../api/dashboard';

export default function AppThreeTeamPage() {
  return (
    <TeamDetailDashboard
      title="应用三组"
      desc=""
      teamCode="APP_THREE"
      fetcher={fetchAppThreeTeamDetail}
      fallbackRows={[]}
      organizationScopeCode="APP_THREE_TEAM_VIEW"
      showPerformance={false}
    />
  );
}
