import TeamDetailDashboard from '../components/TeamDetailDashboard';
import { fetchIntegrationTeamDetail } from '../api/dashboard';
import { integrationTeam } from '../mock/platformData';

export default function IntegrationTeamDetail() {
  return (
    <TeamDetailDashboard
      title="对接组详情"
      desc="重点呈现项目交付、现场支持、需求适配和模块联调工作负载。"
      teamName="对接组"
      fetcher={fetchIntegrationTeamDetail}
      fallbackRows={integrationTeam.map((item) => ({ ...item, team: '对接组' }))}
      composition={[
        { label: '项目对接', percent: '39%', note: '版本适配、需求跟进和跨团队接口推进。', barClass: 'bg-sky-500' },
        { label: '现场支持', percent: '34%', note: '客户现场问题定位、回归验证和问题闭环。', barClass: 'bg-amber-500' },
        { label: '功能交付', percent: '27%', note: '模块发布、交付验收和配置清单梳理。', barClass: 'bg-emerald-500' },
      ]}
      suggestions={[
        {
          title: '流程标准化',
          content: '建议将常见问题处理流程标准化，减少重复性支持工作对骨干成员的消耗。',
          className: 'border-amber-100 bg-amber-50 text-amber-900',
        },
        {
          title: '知识库建设',
          content: '适合建立项目问题知识库与版本适配清单，提升交付人效和稳定性。',
          className: 'border-sky-100 bg-sky-50 text-sky-900',
        },
      ]}
    />
  );
}
