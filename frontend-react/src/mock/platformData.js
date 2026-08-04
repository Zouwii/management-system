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

const PERFORMANCE_QUARTERS = [
  '2024 Q3',
  '2024 Q4',
  '2025 Q1',
  '2025 Q2',
  '2025 Q3',
  '2025 Q4',
  '2026 Q1',
  '2026 Q2',
];

function roundPerformance(value) {
  return Number(value.toFixed(3));
}

function getMockManagerScore(finalScore) {
  if (finalScore >= 2) return 2;
  if (finalScore >= 1.5) return 1.5;
  if (finalScore >= 1.2) return 1.2;
  if (finalScore >= 1) return 1;
  if (finalScore >= 0.8) return 0.8;
  if (finalScore >= 0.5) return 0.5;
  return 0;
}

function buildPerformanceHistory(finalScores, hourScores, carryScores) {
  return PERFORMANCE_QUARTERS.map((quarter, index) => {
    const finalScore = finalScores[index];
    const hourScore = hourScores[index];
    const managerScore = getMockManagerScore(finalScore);
    const previousCarry = index > 0 ? carryScores[index - 1] : 0;
    const overallScore = roundPerformance(hourScore * 0.7 + managerScore * 0.3);
    const balanceScore = roundPerformance(overallScore + previousCarry);
    const carryScore = carryScores[index];

    return {
      quarter,
      hourScore,
      managerScore,
      overallScore,
      balanceScore,
      overflowScore: roundPerformance(Math.max(balanceScore - finalScore, 0)),
      decayScore: roundPerformance(carryScore * 0.25),
      carryScore,
      finalScore,
    };
  });
}

function createPerformanceArchive(targetLabel, scenario, finalScores, hourScores, carryScores) {
  return {
    targetLabel,
    sourceLabel: `界面优化样例 · ${scenario}`,
    desc: `匿名化 ${scenario} 数据，用于验证绩效卡片、档位颜色、季度明细、结余计算和趋势图。`,
    history: buildPerformanceHistory(finalScores, hourScores, carryScores),
  };
}

export const performanceArchives = {
  李四: createPerformanceArchive(
    '李四',
    '稳定提升',
    [0.8, 1.0, 1.0, 1.2, 1.0, 1.2, 1.5, 1.2],
    [0.86, 0.98, 1.03, 1.12, 1.01, 1.15, 1.28, 1.18],
    [0.01, 0.04, 0.07, 0.12, 0.06, 0.14, 0.18, 0.11],
  ),
  王强: createPerformanceArchive(
    '王强',
    '低谷恢复',
    [1.0, 0.8, 0.5, 0.8, 1.0, 0.8, 1.0, 1.0],
    [1.01, 0.91, 0.68, 0.88, 0.99, 0.92, 1.04, 1.06],
    [0.05, 0.02, 0, 0.01, 0.05, 0.02, 0.07, 0.08],
  ),
  陈晨: createPerformanceArchive(
    '陈晨',
    '持续高绩效',
    [1.0, 1.2, 1.2, 1.5, 1.2, 1.5, 1.5, 1.5],
    [1.05, 1.14, 1.18, 1.31, 1.21, 1.36, 1.4, 1.43],
    [0.05, 0.11, 0.14, 0.22, 0.16, 0.25, 0.3, 0.32],
  ),
  赵磊: createPerformanceArchive(
    '赵磊',
    '需要提高',
    [1.0, 1.0, 0.8, 1.0, 0.8, 0.8, 1.0, 0.8],
    [0.99, 1.02, 0.86, 0.97, 0.82, 0.84, 0.96, 0.79],
    [0.04, 0.06, 0.02, 0.05, 0.01, 0, 0.04, 0],
  ),
  孙涛: createPerformanceArchive(
    '孙涛',
    '波动上升',
    [0.8, 1.0, 0.8, 1.0, 1.2, 1.0, 1.2, 1.2],
    [0.83, 0.97, 0.89, 1.03, 1.14, 1.06, 1.18, 1.22],
    [0, 0.03, 0.01, 0.05, 0.12, 0.06, 0.13, 0.16],
  ),
  周凯: createPerformanceArchive(
    '周凯',
    '连续下滑',
    [1.2, 1.0, 1.0, 0.8, 0.8, 0.5, 0.8, 0.5],
    [1.16, 1.04, 0.99, 0.9, 0.84, 0.68, 0.8, 0.61],
    [0.1, 0.07, 0.05, 0.02, 0, 0, 0.01, 0],
  ),
  何俊: createPerformanceArchive(
    '何俊',
    '杰出突破',
    [1.0, 1.2, 1.2, 1.5, 1.5, 1.5, 2.0, 2.0],
    [1.08, 1.18, 1.23, 1.39, 1.45, 1.51, 1.68, 1.76],
    [0.08, 0.14, 0.19, 0.27, 0.34, 0.4, 0.52, 0.6],
  ),
  刘洋: createPerformanceArchive(
    '刘洋',
    '风险预警',
    [1.0, 0.8, 0.8, 0.5, 0.8, 0.5, 0.5, 0.4],
    [0.96, 0.87, 0.81, 0.63, 0.78, 0.59, 0.55, 0.42],
    [0.04, 0.01, 0, 0, 0.01, 0, 0, 0],
  ),
  吴彬: createPerformanceArchive(
    '吴彬',
    '稳定达标',
    [1.0, 1.0, 1.2, 1.0, 1.0, 1.2, 1.0, 1.0],
    [1.01, 1.04, 1.14, 1.02, 1.05, 1.16, 1.08, 1.1],
    [0.04, 0.06, 0.11, 0.07, 0.08, 0.13, 0.09, 0.1],
  ),
  导航主管: createPerformanceArchive(
    '导航主管',
    '主管高绩效',
    [1.0, 1.2, 1.2, 1.2, 1.5, 1.2, 1.5, 1.5],
    [1.08, 1.17, 1.22, 1.25, 1.38, 1.29, 1.44, 1.48],
    [0.06, 0.12, 0.16, 0.2, 0.28, 0.22, 0.31, 0.35],
  ),
  对接主管: createPerformanceArchive(
    '对接主管',
    '主管稳健',
    [1.0, 1.0, 1.2, 1.0, 1.2, 1.2, 1.0, 1.2],
    [1.02, 1.06, 1.15, 1.08, 1.19, 1.22, 1.11, 1.24],
    [0.04, 0.07, 0.12, 0.08, 0.14, 0.17, 0.11, 0.18],
  ),
  系统管理员: createPerformanceArchive(
    '系统管理员',
    '全档位覆盖',
    [0.4, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.0],
    [0.48, 0.62, 0.85, 1.02, 1.18, 1.42, 1.7, 1.82],
    [0, 0, 0.01, 0.05, 0.13, 0.26, 0.5, 0.68],
  ),
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
