export const departmentStats = {
  totalMembers: 9,
  navMembers: 4,
  integrationMembers: 5,
  servoMembers: 5,
  totalHours: 1381,
  quarter: '2026 Q2',
  avgPerformance: 'A-',
  riskCount: 3,
};

export const navTeam = [
  { name: '李四', role: '导航算法工程师', level: 'P6', hours: 156, effectiveRate: '85%', perf: 'A', finalPerformance: 1.2, focus: '路径规划优化 / 控制调优', risk: '低', trend: '+8h' },
  { name: '王强', role: '导航算法工程师', level: 'P5', hours: 149, effectiveRate: '83%', perf: 'B+', finalPerformance: 1.0, focus: 'Frenet绕障 / 回归测试', risk: '中', trend: '+5h' },
  { name: '陈晨', role: '导航软件工程师', level: 'P5', hours: 161, effectiveRate: '87%', perf: 'A-', finalPerformance: 1.2, focus: '任务链路联调 / 日志分析', risk: '低', trend: '+11h' },
  { name: '赵磊', role: '导航算法工程师', level: 'P5', hours: 144, effectiveRate: '81%', perf: 'B+', finalPerformance: 1.0, focus: 'LQR控制器优化', risk: '中', trend: '-2h' },
];

export const integrationTeam = [
  { name: '孙涛', role: '对接工程师', level: 'P5', hours: 163, effectiveRate: '84%', perf: 'A-', finalPerformance: 1.2, focus: '项目接口对接 / 现场问题闭环', risk: '中', trend: '+7h' },
  { name: '周凯', role: '对接工程师', level: 'P5', hours: 151, effectiveRate: '80%', perf: 'B+', finalPerformance: 1.0, focus: '客户需求适配 / 配置支持', risk: '低', trend: '+3h' },
  { name: '何俊', role: '软件工程师', level: 'P6', hours: 158, effectiveRate: '86%', perf: 'A', finalPerformance: 1.2, focus: '地图模块 / 安全模块需求交付', risk: '低', trend: '+9h' },
  { name: '刘洋', role: '软件工程师', level: 'P5', hours: 146, effectiveRate: '79%', perf: 'B', finalPerformance: 0.8, focus: '伺服模块维护 / 功能联调', risk: '中', trend: '-4h' },
  { name: '吴彬', role: '对接工程师', level: 'P5', hours: 154, effectiveRate: '82%', perf: 'A-', finalPerformance: 1.2, focus: '项目问题定位 / 交付支持', risk: '低', trend: '+6h' },
];

export const personalHours = [
  { month: '4月', total: 15.0 * 8 },
  { month: '5月', total: 18.0 * 8 },
  { month: '6月', total: 16.5 * 8 },
];

export const personalHoursDashboard = {
  defaultRange: {
    startDate: '2026-04-01T09:00:00',
    endDate: '2026-06-30T18:00:00',
  },
  lastUpdatedAt: '2026-04-01T10:30:00',
  compensatoryDays: 0,
  statutoryHolidays: [
    { date: '2026-04-06', name: '清明节调休' },
    { date: '2026-05-01', name: '劳动节' },
    { date: '2026-05-04', name: '劳动节调休' },
    { date: '2026-06-22', name: '端午节调休' },
  ],
  scheduledEffectiveHours: 432,
  completedEffectiveHours: 316,
  quarterlyOverdueEffectiveHours: 28,
  quarterlyOverdueCompletedHours: 12,
  quarterlyPlannedEffectiveHours: 64,
  quarterlyPlannedCompletedHours: 48,
  taskDistribution: [
    { type: '产品', hours: 126, ratio: '29%' },
    { type: '订单', hours: 118, ratio: '27%' },
    { type: '研发', hours: 188, ratio: '44%' },
  ],
  taskDetails: [
    { name: '路径规划稳定性优化', hours: 42, type: '研发', quarterCategory: '当前季度排期', status: '未完成', deadline: '2026-04-18', link: 'https://www.teambition.com/task/route-plan-001' },
    { name: '导航参数产品化配置梳理', hours: 24, type: '产品', quarterCategory: '当前季度排期', status: '已完成', deadline: '2026-04-26', link: 'https://www.teambition.com/task/product-nav-002' },
    { name: '订单项目 A 现场问题闭环', hours: 38, type: '订单', quarterCategory: '季度逾期排期', status: '未完成', deadline: '2026-04-29', link: 'https://www.teambition.com/task/order-field-003' },
    { name: '控制器边界工况回归', hours: 31, type: '研发', quarterCategory: '当前季度排期', status: '未完成', deadline: '2026-05-09', link: 'https://www.teambition.com/task/control-regression-004' },
    { name: '订单项目 B 版本适配', hours: 27, type: '订单', quarterCategory: '季度逾期排期', status: '未完成', deadline: '2026-05-14', link: 'https://www.teambition.com/task/order-adapter-005' },
    { name: '产品需求评审与拆解', hours: 19, type: '产品', quarterCategory: '当前季度排期', status: '已完成', deadline: '2026-05-18', link: 'https://www.teambition.com/task/product-review-006' },
    { name: '复杂场景日志复盘', hours: 23, type: '研发', quarterCategory: '当前季度排期', status: '已完成', deadline: '2026-05-21', link: 'https://www.teambition.com/task/log-review-007' },
    { name: '订单项目 C 交付联调', hours: 26, type: '订单', quarterCategory: '季度逾期排期', status: '未完成', deadline: '2026-05-28', link: 'https://www.teambition.com/task/order-delivery-008' },
    { name: '订单项目 E 客户现场复测', hours: 22, type: '订单', quarterCategory: '当前季度排期', status: '已完成', deadline: '2026-05-30', link: 'https://www.teambition.com/task/order-retest-015' },
    { name: '路径规划专项方案沉淀', hours: 18, type: '研发', quarterCategory: '季度逾期排期', status: '已完成', deadline: '2026-06-05', link: 'https://www.teambition.com/task/route-doc-009' },
    { name: '产品配置项体验改进', hours: 16, type: '产品', quarterCategory: '当前季度排期', status: '已完成', deadline: '2026-06-10', link: 'https://www.teambition.com/task/product-config-010' },
    { name: '历史订单 D 遗留问题回归', hours: 21, type: '订单', quarterCategory: '季度逾期排期', status: '未完成', deadline: '2026-06-14', link: 'https://www.teambition.com/task/order-legacy-011' },
    { name: '订单项目 F 版本灰度验证', hours: 29, type: '订单', quarterCategory: '当前季度排期', status: '未完成', deadline: '2026-06-16', link: 'https://www.teambition.com/task/order-gray-016' },
    { name: '旧版地图模块兼容修复', hours: 17, type: '研发', quarterCategory: '季度逾期排期', status: '已完成', deadline: '2026-06-18', link: 'https://www.teambition.com/task/map-legacy-012' },
    { name: '产品配置缺陷补丁处理', hours: 14, type: '产品', quarterCategory: '季度逾期排期', status: '未完成', deadline: '2026-06-21', link: 'https://www.teambition.com/task/product-patch-013' },
    { name: '本季度控制链路稳定性验证', hours: 20, type: '研发', quarterCategory: '当前季度排期', status: '未完成', deadline: '2026-06-26', link: 'https://www.teambition.com/task/control-verify-014' },
    { name: '订单项目 G 上线后回访闭环', hours: 18, type: '订单', quarterCategory: '季度逾期排期', status: '已完成', deadline: '2026-06-27', link: 'https://www.teambition.com/task/order-followup-017' },
  ],
};

export const performanceArchives = {
  李四: {
    targetLabel: '李四',
    sourceLabel: '匿名样例 A',
    desc: '当前页面使用匿名化归档样例展示季度绩效与结余绩效，不映射任何真实人员信息。',
    history: [
      { quarter: '2024 Q4', hourScore: 1.05, managerScore: 1, overallScore: 1.035, balanceScore: 1.035, overflowScore: 0.035, decayScore: 0.009, carryScore: 0.035, finalScore: 1.0 },
      { quarter: '2025 Q1', hourScore: 1.02, managerScore: 1.2, overallScore: 1.074, balanceScore: 1.109, overflowScore: 0.074, decayScore: 0.025, carryScore: 0.100, finalScore: 1.0 },
      { quarter: '2025 Q2', hourScore: 1.05, managerScore: 1.2, overallScore: 1.095, balanceScore: 1.195, overflowScore: 0.095, decayScore: 0.043, carryScore: 0.170, finalScore: 1.0 },
      { quarter: '2025 Q3', hourScore: 1.05, managerScore: 1.2, overallScore: 1.095, balanceScore: 1.265, overflowScore: 0.095, decayScore: 0.006, carryScore: 0.022, finalScore: 1.2 },
      { quarter: '2025 Q4', hourScore: 0.93, managerScore: 1.0, overallScore: 0.951, balanceScore: 0.973, overflowScore: 0.151, decayScore: 0.042, carryScore: 0.168, finalScore: 0.8 },
    ],
  },
  王主管: {
    targetLabel: '王主管',
    sourceLabel: '匿名样例 B',
    desc: '主管账号使用匿名化归档样例数据，保留季度最终绩效和结余绩效口径。',
    history: [
      { quarter: '2024 Q4', hourScore: 1.0, managerScore: 1.0, overallScore: 1.041, balanceScore: 1.070, overflowScore: 0.041, decayScore: 0.016, carryScore: 0.063, finalScore: 1.0 },
      { quarter: '2025 Q1', hourScore: 0.98, managerScore: 1.0, overallScore: 0.976, balanceScore: 1.039, overflowScore: 0.176, decayScore: 0.009, carryScore: 0.023, finalScore: 1.0 },
      { quarter: '2025 Q2', hourScore: 1.0, managerScore: 1.0, overallScore: 1.0, balanceScore: 1.023, overflowScore: 0.039, decayScore: 0.012, carryScore: 0.017, finalScore: 1.0 },
      { quarter: '2025 Q3', hourScore: 0.91, managerScore: 1.0, overallScore: 0.897, balanceScore: 0.914, overflowScore: 0.097, decayScore: 0.028, carryScore: 0.110, finalScore: 0.8 },
      { quarter: '2025 Q4', hourScore: 1.0, managerScore: 1.0, overallScore: 1.0, balanceScore: 1.110, overflowScore: 0.000, decayScore: 0.021, carryScore: 0.083, finalScore: 1.0 },
    ],
  },
  系统管理员: {
    targetLabel: '系统管理员',
    sourceLabel: '匿名样例 C',
    desc: '管理员账号使用匿名化高档位样例，便于验证结余绩效累计和颜色态。',
    history: [
      { quarter: '2024 Q4', hourScore: 1.13, managerScore: 1.0, overallScore: 1.091, balanceScore: 1.091, overflowScore: 0.091, decayScore: 0.023, carryScore: 0.091, finalScore: 1.0 },
      { quarter: '2025 Q1', hourScore: 1.08, managerScore: 1.2, overallScore: 1.116, balanceScore: 1.207, overflowScore: 0.116, decayScore: 0.000, carryScore: 0.000, finalScore: 1.2 },
      { quarter: '2025 Q2', hourScore: 1.13, managerScore: 1.2, overallScore: 1.151, balanceScore: 1.151, overflowScore: 0.151, decayScore: 0.038, carryScore: 0.151, finalScore: 1.0 },
      { quarter: '2025 Q3', hourScore: 1.11, managerScore: 1.2, overallScore: 1.137, balanceScore: 1.370, overflowScore: 0.019, decayScore: 0.033, carryScore: 0.132, finalScore: 1.2 },
      { quarter: '2025 Q4', hourScore: 1.07, managerScore: 1.0, overallScore: 1.049, balanceScore: 1.181, overflowScore: 0.049, decayScore: 0.037, carryScore: 0.148, finalScore: 1.0 },
    ],
  },
};

export const aiInsightList = [
  {
    title: '工时结构建议',
    type: '效率优化',
    content: '你当前联调支持工时占比仍偏高，建议将算法验证任务按周拆分并固定在上午深度时段处理。',
  },
  {
    title: '绩效提升建议',
    type: '绩效关联',
    content: '当前个人绩效已进入A档，但高价值任务成果展示仍可加强，建议补充方案文档与问题闭环案例。',
  },
  {
    title: '风险提醒',
    type: '负载预警',
    content: '近两周复杂问题排查任务连续增加，若继续攀升，可能挤压研发型任务时间。',
  },
  {
    title: '成长建议',
    type: '能力发展',
    content: '适合继续承担控制器优化、复杂问题定位和技术规范建设类任务，提升技术影响力。',
  },
];

export const allRows = [
  ...navTeam.map((item) => ({ ...item, team: '导航组' })),
  ...integrationTeam.map((item) => ({ ...item, team: '对接组' })),
];

export const permissionMatrix = [
  ['菜单权限', '决定可见Tab和导航菜单', '仅个人端3个菜单', '主管端全部业务菜单', '全部菜单'],
  ['页面权限', '决定是否可进入页面', '仅个人工时/绩效/AI页', '可进部门、组、个人、权限页', '全部页面'],
  ['按钮权限', '导出、配置、调整、审批等操作', '无管理类按钮', '导出/点评/查看建议', '全量操作'],
  ['数据权限', '本人、组级、部门级、全局数据范围', '本人', '本人+所管组/部门', '全局'],
  ['字段权限', '敏感字段脱敏展示', '隐藏他人工资/敏感评价', '可见业务字段', '可配置字段范围'],
];
