import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  fetchPersonalHoursMembers,
  queryPersonalHours,
  increaseSync,
} from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import { ROLES } from '../constants/roles';
import EmployeeLayout from '../layouts/EmployeeLayout';
import {
  personalHours as fallbackTrend,
  personalHoursDashboard as fallbackDashboard,
} from '../mock/platformData';
import {
  buildMonthlyTrend,
  formatDateTime,
  getDeltaStatus,
} from '../utils/workHours';
import { shouldHideMemberInSelector } from '../utils/memberVisibility';
import { useAuthStore } from '../store/authStore';

export default function PersonalHours({ forceCanViewAllPeople = null }) {
  const user = useAuthStore((state) => state.user);
  const canViewAllByRole = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const canViewAllPeople = typeof forceCanViewAllPeople === 'boolean' ? forceCanViewAllPeople : canViewAllByRole;
  const [searchParams, setSearchParams] = useSearchParams();
  const targetFromQuery = searchParams.get('target') ?? '';
  const initialTargetRef = useRef('');
  if (!initialTargetRef.current) {
    initialTargetRef.current = canViewAllPeople
      ? (targetFromQuery || user?.user_id || user?.name || 'ALL')
      : (user?.user_id || user?.name || '');
  }
  const defaultTarget = initialTargetRef.current;
  const [sourceTrend, setSourceTrend] = useState(fallbackTrend);
  const [dashboard, setDashboard] = useState(fallbackDashboard);
  const [dateRange, setDateRange] = useState(fallbackDashboard.defaultRange);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(fallbackDashboard.lastUpdatedAt ?? '');
  const [compensatoryDays, setCompensatoryDays] = useState(fallbackDashboard.compensatoryDays ?? 0);
  const [memberOptions, setMemberOptions] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState(defaultTarget);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [taskFilter, setTaskFilter] = useState('全部');
  const [quarterFilter, setQuarterFilter] = useState('全部');
  const [statusFilter, setStatusFilter] = useState('全部');
  const [taskSort, setTaskSort] = useState('desc');
  const [isQuerying, setIsQuerying] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const [showBusyModal, setShowBusyModal] = useState(false);
  const [quickRangePreset, setQuickRangePreset] = useState('quarter_to_today');
  const [selectedTeam, setSelectedTeam] = useState('');
  const [hourStatusMember, setHourStatusMember] = useState('ALL');
  const [hourStatusAllocationSort, setHourStatusAllocationSort] = useState('none');
  const [hourStatusCompletionSort, setHourStatusCompletionSort] = useState('none');
  const [hourStatusRange, setHourStatusRange] = useState('quarter');
  const latestQueryRequestIdRef = useRef(0);
  const isAdmin = user?.role === ROLES.ADMIN;
  const isManager = user?.role === ROLES.MANAGER;

  const normalizeMemberOptionsForViewer = (options = []) => {
    const list = Array.isArray(options) ? options : [];
    return list.filter((option) => !shouldHideMemberInSelector(option));
  };

  function pickConcreteTarget(options = [], preferred = '') {
    const normalizedPreferred = String(preferred || '').trim();
    const normalizedOptions = (Array.isArray(options) ? options : [])
      .map((item) => String(item?.id || '').trim())
      .filter(Boolean);
    if (normalizedPreferred && normalizedPreferred !== 'ALL' && normalizedOptions.includes(normalizedPreferred)) {
      return normalizedPreferred;
    }
    const firstNonAll = normalizedOptions.find((id) => id !== 'ALL');
    if (firstNonAll) return firstNonAll;
    return normalizedPreferred || normalizedOptions[0] || '';
  }

  function buildEmptyDashboardByRange(range) {
    return {
      ...fallbackDashboard,
      defaultRange: {
        startDate: range?.startDate || fallbackDashboard.defaultRange?.startDate || '',
        endDate: range?.endDate || fallbackDashboard.defaultRange?.endDate || '',
      },
      scheduledEffectiveHours: 0,
      completedEffectiveHours: 0,
      quarterlyOverdueEffectiveHours: 0,
      quarterlyOverdueCompletedHours: 0,
      quarterlyPlannedEffectiveHours: 0,
      quarterlyPlannedCompletedHours: 0,
      currentQuarterWorkdayCosthourSum: 0,
      softwareDevHours: 0,
      issueHandlingHours: 0,
      taskDistribution: [],
      taskDetails: [],
    };
  }

  async function runInitialQuery(target) {
    const initialRange = buildQuarterRange(true);
    const payload = {
      ...initialRange,
      target,
    };
    const response = await queryPersonalHours(user, payload);
    return { payload, response };
  }

  useEffect(() => {
    let active = true;

    const init = async () => {
      if (canViewAllPeople) {
        const membersRes = await fetchPersonalHoursMembers(user);
        if (!active) return;
        const nextMemberOptions = normalizeMemberOptionsForViewer(membersRes?.data?.memberOptions ?? []);
        const availableTargets = new Set(nextMemberOptions.map((item) => String(item?.id || '')));
        const targetFromUrl = String(defaultTarget || '').trim();
        const preferredTarget = availableTargets.has(targetFromUrl)
          ? targetFromUrl
          : (membersRes?.data?.selectedTarget ?? targetFromUrl);
        const nextTarget = pickConcreteTarget(
          nextMemberOptions,
          availableTargets.has(String(preferredTarget || ''))
            ? String(preferredTarget || '')
            : (nextMemberOptions[0]?.id ?? defaultTarget),
        );
        setMemberOptions(nextMemberOptions);
        // 下拉框保持“当前选中人”，但首屏数据统一按 ALL 预取，保证成员全集/聚合数据就绪。
        setSelectedTarget(nextTarget);
        const { payload, response } = await runInitialQuery('ALL');
        if (!active) return;
        setSourceTrend([]);
        setDashboard(buildEmptyDashboardByRange(payload));
        setDateRange({
          startDate: payload.startDate,
          endDate: payload.endDate,
        });
        setQuickRangePreset('quarter_to_today');
        setLastUpdatedAt(response?.data?.dashboard?.lastUpdatedAt ?? '');
        setCompensatoryDays(0);
      } else {
        const { payload, response } = await runInitialQuery(defaultTarget);
        if (!active) return;
        setSourceTrend(response.data.trend ?? fallbackTrend);
        setDashboard(response.data.dashboard ?? fallbackDashboard);
        setDateRange({
          startDate: payload.startDate,
          endDate: payload.endDate,
        });
        setQuickRangePreset('quarter_to_today');
        setLastUpdatedAt(response.data.dashboard?.lastUpdatedAt ?? '');
        setCompensatoryDays(response.data.dashboard?.compensatoryDays ?? 0);
        setMemberOptions(response.data.memberOptions ?? []);
        setSelectedTarget(response.data.selectedTarget ?? defaultTarget);
      }
    };

    init();

    return () => {
      active = false;
    };
  }, [canViewAllPeople, user]);

  const workhourCharacterCoefficients = useMemo(() => {
    const fromDashboard = dashboard.workhourCharacterCoefficients;
    if (fromDashboard && typeof fromDashboard === 'object') return fromDashboard;
    return { 0: 0.4, 1: 0.7, 2: 0.7, 3: 1.0, 4: 0.7 };
  }, [dashboard.workhourCharacterCoefficients]);
  const selectedCharacter = useMemo(() => {
    if (canViewAllPeople) {
      const hit = memberOptions.find((x) => String(x?.id || '') === String(selectedTarget || ''));
      if (hit && hit.character !== undefined && hit.character !== null && String(hit.character).trim() !== '') {
        return Number(hit.character);
      }
    }
    return Number(user?.character ?? 1);
  }, [canViewAllPeople, memberOptions, selectedTarget, user?.character]);
  const expectedCoefficient = useMemo(() => {
    const backendCoeff = Number(dashboard.expectedCoefficient);
    if (Number.isFinite(backendCoeff) && backendCoeff > 0) {
      return backendCoeff;
    }
    const key = String(Number.isFinite(selectedCharacter) ? selectedCharacter : 1);
    const v = Number(workhourCharacterCoefficients?.[key]);
    return Number.isFinite(v) && v > 0 ? v : 1.0;
  }, [dashboard.expectedCoefficient, selectedCharacter, workhourCharacterCoefficients]);
  const baseWorkdayCount = Number(dashboard.workdayCount || 0);
  const expectedWorkdayCount = Math.max(baseWorkdayCount - Number(compensatoryDays || 0), 0);
  const expectedEffectiveDays = expectedWorkdayCount * expectedCoefficient;  // 工时数据总览用（乘系数）
  const rawExpectedWorkdays = expectedWorkdayCount;  // 工作日耗时柱状图用（不乘系数）
  const memberGroupOptions = useMemo(() => {
    if (!canViewAllPeople) return [];
    const navMembers = memberOptions.filter((option) => option.team === '导航组');
    const integrationMembers = memberOptions.filter((option) => option.team === '对接组');
    const others = memberOptions.filter((option) => !['全部', '导航组', '对接组'].includes(String(option.team || '')));
    return [
      { label: '导航组', options: navMembers },
      { label: '对接组', options: integrationMembers },
      ...(others.length ? [{ label: '其他', options: others }] : []),
    ].filter((group) => group.options.length > 0);
  }, [canViewAllPeople, memberOptions]);
  const visibleTeamMembers = useMemo(
    () => memberGroupOptions.find((group) => group.label === selectedTeam)?.options ?? [],
    [memberGroupOptions, selectedTeam],
  );
  const hourStatusMemberOptions = useMemo(() => {
    const base = (memberOptions || [])
      .filter((option) => String(option?.id || '').trim() && String(option?.id || '').trim() !== 'ALL')
      .map((option) => ({
        id: String(option.id),
        name: String(option.name || option.id),
      }));
    return [{ id: 'ALL', name: '全部成员' }, ...base];
  }, [memberOptions]);

  useEffect(() => {
    if (!canViewAllPeople) return;
    if (!memberGroupOptions.length) return;
    const hitGroup = memberGroupOptions.find((group) => group.options.some((option) => String(option.id) === String(selectedTarget)));
    if (hitGroup) {
      if (selectedTeam !== hitGroup.label) {
        setSelectedTeam(hitGroup.label);
      }
      return;
    }
    if (!selectedTeam || !memberGroupOptions.some((group) => group.label === selectedTeam)) {
      setSelectedTeam(memberGroupOptions[0].label);
    }
  }, [canViewAllPeople, memberGroupOptions, selectedTarget, selectedTeam]);

  const scheduledDelta = dashboard.scheduledEffectiveHours + dashboard.quarterlyOverdueEffectiveHours - expectedEffectiveDays;
  const completedDelta = dashboard.completedEffectiveHours + dashboard.quarterlyOverdueCompletedHours - expectedEffectiveDays;
  const softwareWorkdayCostHour = useMemo(() => {
    const n = Number(dashboard.softwareDevHours);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }, [dashboard.softwareDevHours]);
  const issueWorkdayCostHour = useMemo(() => {
    const n = Number(dashboard.issueHandlingHours);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }, [dashboard.issueHandlingHours]);
  const filledWorkdayDays = softwareWorkdayCostHour + issueWorkdayCostHour;
  // 口径：已填工作日 - 总工作日
  const workdayFilledDelta = filledWorkdayDays - expectedWorkdayCount;
  const scheduledStatus = getDeltaStatus(scheduledDelta);
  const completedStatus = getDeltaStatus(completedDelta);
  const workdayFilledStatus = getDeltaStatus(workdayFilledDelta);
  const trend = useMemo(
    () => buildMonthlyTrend(
      sourceTrend,
      dashboard.taskDetails.filter((t) => t?.quarterCategory !== '季度逾期排期'),
    ).map((item) => ({
      ...item,
      // 月度“预期有效工时”：法定工作日按当前查看对象系数折算
      total: Number(item.total || 0) * expectedCoefficient,
    })),
    [dashboard.taskDetails, expectedCoefficient, sourceTrend],
  );
  const maxTrendValue = Math.max(...trend.flatMap((item) => [item.total, item.effective, item.completed]), 1);
  const distributionBarClassMap = {
    产品: 'bg-emerald-500',
    订单: 'bg-amber-500',
    研发: 'bg-violet-500',
    无: 'bg-rose-500',
  };
  const taskNatureBarClassMap = {
    自主型: 'bg-[#10b981]',
    指派型: 'bg-[#d04934]',
    能力型: 'bg-[#1b9aee]',
    无: 'bg-slate-400',
  };
  const quarterTagClassMap = {
    当前季度: 'border-sky-100 bg-sky-50 text-sky-700',
    季度逾期: 'border-amber-100 bg-amber-50 text-amber-700',
  };
  const statusTagClassMap = {
    创建中: 'border-yellow-200 bg-yellow-50 text-yellow-800',
    待评审: 'border-indigo-100 bg-indigo-50 text-indigo-700',
    评审中: 'border-slate-200 bg-slate-100 text-slate-700',
    搁置: 'border-amber-100 bg-amber-50 text-amber-700',
    已完成: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    未完成: 'border-blue-100 bg-blue-50 text-blue-700',
  };
  const taskTypeTagClassMap = {
    产品: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    订单: 'border-amber-100 bg-amber-50 text-amber-700',
    研发: 'border-violet-100 bg-violet-50 text-violet-700',
    无: 'border-rose-100 bg-rose-50 text-rose-700',
  };
  const taskNatureTagClassMap = {
    自主型: 'border-[#10b981]/20 bg-[#10b981]/10 text-[#059669]',
    能力型: 'border-[#1b9aee]/20 bg-[#1b9aee]/10 text-[#1b9aee]',
    指派型: 'border-[#d04934]/20 bg-[#d04934]/10 text-[#d04934]',
    无: 'border-slate-200 bg-slate-50 text-slate-600',
  };
  const taskTypeOptions = ['全部', '产品', '订单', '研发', '无'];
  const quarterFilterOptions = ['全部', '当前季度', '季度逾期'];
  const statusFilterOptions = ['全部', '创建中', '未完成', '待评审', '评审中', '已完成', '搁置'];
  const filteredTasks = useMemo(() => {
    const nextTasks = dashboard.taskDetails
      .filter((task) => taskFilter === '全部' || task.type === taskFilter)
      .filter((task) => {
        if (quarterFilter === '全部') return true;
        const normalized = String(task.quarterCategory || '')
          .replace('当前季度排期', '当前季度')
          .replace('季度逾期排期', '季度逾期');
        return normalized === quarterFilter;
      })
      .filter((task) => statusFilter === '全部' || task.status === statusFilter)
      .sort((left, right) => (taskSort === 'desc' ? right.hours - left.hours : left.hours - right.hours));
    const idSet = new Set(nextTasks.map((task) => String(task.taskId || '').trim()).filter(Boolean));
    const childrenByParent = new Map();
    const stableOrder = new Map();
    nextTasks.forEach((task, index) => {
      stableOrder.set(String(task.taskId || '').trim(), index);
      const parentId = String(task.parent_task_id || '').trim();
      const taskId = String(task.taskId || '').trim();
      if (!taskId || !parentId || !idSet.has(parentId)) return;
      const bucket = childrenByParent.get(parentId) || [];
      bucket.push(task);
      childrenByParent.set(parentId, bucket);
    });
    const roots = nextTasks.filter((task) => {
      const parentId = String(task.parent_task_id || '').trim();
      return !parentId || !idSet.has(parentId);
    });
    const ordered = [];
    const visited = new Set();
    const appendNode = (task) => {
      const taskId = String(task.taskId || '').trim();
      if (!taskId || visited.has(taskId)) return;
      visited.add(taskId);
      ordered.push(task);
      const children = (childrenByParent.get(taskId) || [])
        .slice()
        .sort((a, b) => (stableOrder.get(String(a.taskId || '').trim()) ?? 0) - (stableOrder.get(String(b.taskId || '').trim()) ?? 0));
      children.forEach(appendNode);
    };
    roots.forEach(appendNode);
    nextTasks.forEach(appendNode);
    return ordered;
  }, [dashboard.taskDetails, quarterFilter, showAllTasks, statusFilter, taskFilter, taskSort]);
  const visibleTasks = filteredTasks;
  const visibleTaskIds = useMemo(
    () => new Set(visibleTasks.map((task) => String(task.taskId || '').trim()).filter(Boolean)),
    [visibleTasks],
  );
  const visibleTaskParentMap = useMemo(() => {
    const m = new Map();
    visibleTasks.forEach((task) => {
      const taskId = String(task.taskId || '').trim();
      if (!taskId) return;
      m.set(taskId, String(task.parent_task_id || '').trim());
    });
    return m;
  }, [visibleTasks]);
  const visibleTaskDepthMap = useMemo(() => {
    const depthMemo = new Map();
    const calcDepth = (taskId, path = new Set()) => {
      if (!taskId) return 0;
      if (depthMemo.has(taskId)) return depthMemo.get(taskId);
      if (path.has(taskId)) return 0;
      path.add(taskId);
      const parentId = String(visibleTaskParentMap.get(taskId) || '').trim();
      let depth = 0;
      if (parentId && parentId !== taskId && visibleTaskParentMap.has(parentId)) {
        depth = calcDepth(parentId, path) + 1;
      }
      depthMemo.set(taskId, depth);
      path.delete(taskId);
      return depth;
    };
    visibleTaskParentMap.forEach((_parentId, taskId) => {
      calcDepth(taskId);
    });
    return depthMemo;
  }, [visibleTaskParentMap]);

  const overdueTaskCount = dashboard.taskDetails.filter((task) => task.quarterCategory === '季度逾期排期').length;
  const currentQuarterTaskCount = dashboard.taskDetails.filter((task) => task.quarterCategory === '当前季度排期').length;
  const completedTaskCount = dashboard.taskDetails.filter((task) => task.status === '已完成').length;
  const pendingTaskCount = dashboard.taskDetails.filter((task) => task.status === '未完成').length;
  const currentQuarterDistribution = useMemo(() => {
    const currentQuarterTasks = dashboard.taskDetails.filter((task) => task.quarterCategory === '当前季度排期');
    const totalHours = currentQuarterTasks.reduce((sum, task) => sum + task.hours, 0);

    return ['产品', '订单', '研发', '无'].map((type) => {
      const hours = currentQuarterTasks
        .filter((task) => task.type === type)
        .reduce((sum, task) => sum + task.hours, 0);
      const ratio = totalHours > 0 ? `${Math.round((hours / totalHours) * 100)}%` : '0%';

      return {
        type,
        hours,
        ratio,
      };
    });
  }, [dashboard.taskDetails]);
  const currentQuarterNatureDistribution = useMemo(() => {
    const currentQuarterTasks = dashboard.taskDetails.filter((task) => task.quarterCategory === '当前季度排期');
    const totalHours = currentQuarterTasks.reduce((sum, task) => sum + task.hours, 0);

    return ['自主型', '指派型', '能力型', '无'].map((nature) => {
      const hours = currentQuarterTasks
        .filter((task) => (task.taskNature || '无') === nature)
        .reduce((sum, task) => sum + task.hours, 0);
      const ratio = totalHours > 0 ? `${Math.round((hours / totalHours) * 100)}%` : '0%';
      return { nature, hours, ratio };
    });
  }, [dashboard.taskDetails]);
  const hourComposition = useMemo(() => {
    const backendSoftware = Number(dashboard.softwareDevHours);
    const backendIssue = Number(dashboard.issueHandlingHours);
    let effectiveHours = 0;
    let costHours = 0;
    if (Number.isFinite(backendSoftware) && Number.isFinite(backendIssue) && (backendSoftware >= 0) && (backendIssue >= 0)) {
      effectiveHours = backendSoftware;
      costHours = backendIssue;
    } else {
      const rows = dashboard.taskDetails || [];
      rows.forEach((task) => {
        const rawEffective = Number(task.hours || task.work_hour || 0);
        const rawCost = Number(task.workday_costhour ?? 0);
        effectiveHours += Number.isFinite(rawEffective) ? rawEffective : 0;
        costHours += Number.isFinite(rawCost) ? rawCost : 0;
      });
    }
    const total = effectiveHours + costHours;
    const effectiveRatio = total > 0 ? Math.round((effectiveHours / total) * 100) : 0;
    const costRatio = total > 0 ? 100 - effectiveRatio : 0;
    return { effectiveHours, costHours, effectiveRatio, costRatio };
  }, [dashboard.taskDetails]);
  const monthlyWorkdayData = useMemo(() => {
    const normalizeMonthLabel = (rawMonth) => {
      const txt = String(rawMonth || '').trim();
      if (!txt) return '';
      if (txt.endsWith('月')) return `${Number(txt.replace('月', ''))}月`;
      const hit = txt.match(/(\d{1,2})月/);
      if (hit) return `${Number(hit[1])}月`;
      const isoHit = txt.match(/^\d{4}-(\d{1,2})/);
      if (isoHit) return `${Number(isoHit[1])}月`;
      const plainHit = txt.match(/^(\d{1,2})$/);
      if (plainHit) return `${Number(plainHit[1])}月`;
      return '';
    };
    const bucket = new Map(
      sourceTrend.map((item) => {
        const month = String(item.month || '').trim();
        return [month, {
          month,
          expected: Number(item.total || 0),
          filled: 0,
        }];
      }).filter(([month]) => Boolean(month)),
    );
    (dashboard.taskDetails || []).forEach((task) => {
      const deadline = String(task.deadline || '').trim();
      if (!deadline) return;
      const parts = deadline.split('-');
      if (parts.length < 2) return;
      const month = `${Number(parts[1])}月`;
      // 与“工时数据”保持同月份口径：只累计已存在月份
      if (!bucket.has(month)) return;
      const raw = Number(task.workday_costhour ?? 0);
      if (Number.isFinite(raw)) {
        bucket.get(month).filled += raw;
      }
    });
    (Array.isArray(dashboard.issueMonthlyCostHours) ? dashboard.issueMonthlyCostHours : []).forEach((item) => {
      const month = normalizeMonthLabel(item?.month);
      if (!month || !bucket.has(month)) return;
      const raw = Number(item?.hours || 0);
      if (!Number.isFinite(raw)) return;
      bucket.get(month).filled += raw;
    });
    return Array.from(bucket.values())
      .sort((a, b) => Number(String(a.month).replace('月', '')) - Number(String(b.month).replace('月', '')));
  }, [dashboard.issueMonthlyCostHours, dashboard.taskDetails, sourceTrend]);
  const maxMonthlyWorkdayValue = Math.max(
    ...monthlyWorkdayData.flatMap((item) => [Number(item.expected || 0), Number(item.filled || 0)]),
    1,
  );

  function formatInputDateTime(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
  }

  function formatRawDays(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toFixed(1) : '0.0';
  }

  function buildQuarterRange(useTodayEnd = false) {
    const now = new Date();
    const currentMonth = now.getMonth();
    const quarterStartMonth = Math.floor(currentMonth / 3) * 3;
    const start = new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0);
    const end = useTodayEnd
      ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59)
      : new Date(now.getFullYear(), quarterStartMonth + 3, 0, 23, 59, 59);

    return {
      startDate: formatInputDateTime(start),
      endDate: formatInputDateTime(end),
      compensatoryDays,
      target: selectedTarget,
    };
  }

  function buildLastQuarterRange() {
    const now = new Date();
    const currentMonth = now.getMonth();
    const currentQuarter = Math.floor(currentMonth / 3);
    // 上季度起始月
    const lastQuarterStartMonth = currentQuarter === 0 ? 9 : (currentQuarter - 1) * 3;
    const lastQuarterYear = currentQuarter === 0 ? now.getFullYear() - 1 : now.getFullYear();
    const start = new Date(lastQuarterYear, lastQuarterStartMonth, 1, 0, 0, 0);
    const end = new Date(lastQuarterYear, lastQuarterStartMonth + 3, 0, 23, 59, 59);

    return {
      startDate: formatInputDateTime(start),
      endDate: formatInputDateTime(end),
      compensatoryDays,
      target: selectedTarget,
    };
  }

  function handleDateChange(field, value) {
    setQuickRangePreset('');
    setDateRange((prev) => {
      const next = {
        ...prev,
        [field]: value,
      };
      // 前端限制：结束时间不能早于开始时间
      if (next.startDate && next.endDate && next.endDate < next.startDate) {
        if (field === 'startDate') {
          next.endDate = next.startDate;
        } else {
          next.startDate = next.endDate;
        }
      }
      return next;
    });
  }

  function resetTaskControls() {
    setTaskFilter('全部');
    setQuarterFilter('全部');
    setStatusFilter('全部');
    setTaskSort('desc');
    setShowAllTasks(false);
  }

  function isUpdateBusyError(error) {
    const text = String(error?.message || '').toLowerCase();
    return text.includes('更新中') || text.includes('update is in progress');
  }

  function showBusyHint() {
    setShowBusyModal(true);
    setActionMessage('正在更新中，暂时无法查询');
  }

  async function handleQuery(payload = { ...dateRange, compensatoryDays }) {
    const requestId = ++latestQueryRequestIdRef.current;
    const normalizedSelectedTarget = pickConcreteTarget(memberOptions, selectedTarget);
    const normalizedPayloadTarget = String(payload?.target || '').trim();
    const resolvedTarget = canViewAllPeople
      ? (normalizedSelectedTarget || normalizedPayloadTarget || 'ALL')
      : (normalizedPayloadTarget || normalizedSelectedTarget || user?.user_id || user?.name || '');
    const queryPayload = {
      ...payload,
      target: resolvedTarget,
      compensatoryDays: payload?.compensatoryDays ?? compensatoryDays,
    };

    if (queryPayload?.startDate && queryPayload?.endDate && queryPayload.endDate < queryPayload.startDate) {
      setActionMessage('结束时间不能早于开始时间。');
      return;
    }
    setIsQuerying(true);
    setActionMessage('');

    try {
      const response = await queryPersonalHours(user, queryPayload);
      if (requestId !== latestQueryRequestIdRef.current) return;
      setSourceTrend(response.data.trend ?? fallbackTrend);
      setDashboard(response.data.dashboard);
      setLastUpdatedAt((current) => response.data.dashboard.lastUpdatedAt ?? current);
      setCompensatoryDays(response.data.dashboard.compensatoryDays ?? 0);
      const nextMemberOptions = normalizeMemberOptionsForViewer(response.data.memberOptions ?? memberOptions);
      setMemberOptions(nextMemberOptions);
      const availableTargets = new Set(nextMemberOptions.map((item) => String(item?.id || '')));
      // 查询后优先保持“本次查询目标”，避免被后端回退值（如 ALL）覆盖。
      const rawNextTarget = queryPayload.target ?? selectedTarget;
      const nextTarget = availableTargets.has(String(rawNextTarget || ''))
        ? rawNextTarget
        : (nextMemberOptions[0]?.id ?? rawNextTarget);
      setSelectedTarget(nextTarget);
      if (canViewAllPeople && nextTarget) {
        setSearchParams({ target: nextTarget });
      }
      setActionMessage('');
    } catch (error) {
      if (isUpdateBusyError(error)) {
        showBusyHint();
        return;
      }
      setActionMessage(`查询失败：${error?.message || '未知错误'}`);
    } finally {
      setIsQuerying(false);
    }
  }

  async function handleUpdate() {
    setIsUpdating(true);
    setActionMessage('');

    try {
      const response = await increaseSync(user);
      const d = response?.data || {};
      setLastUpdatedAt(d.beijing_now ?? lastUpdatedAt);
      const dev = d.dev || {};
      const issue = d.issue || {};
      const devOk = dev.ok ?? 0;
      const devFail = dev.fail ?? 0;
      const issueOk = issue.ok ?? 0;
      const issueFail = issue.fail ?? 0;
      const totalOk = devOk + issueOk;
      const totalFail = devFail + issueFail;
      setActionMessage(
        `已同步 DEV ${devOk}/${d.user_count ?? '?'}人`
        + (devFail ? `(${devFail}失败)` : '')
        + `，Issue ${issueOk}/${d.user_count ?? '?'}人`
        + (issueFail ? `(${issueFail}失败)` : '')
        + (totalFail ? `，共${totalFail}失败` : '')
      );
    } catch (error) {
      if (isUpdateBusyError(error)) {
        showBusyHint();
        return;
      }
      setActionMessage(`更新失败：${error?.message || '未知错误'}`);
    } finally {
      setIsUpdating(false);
    }
  }

  function escapeCsvCell(value) {
    const text = value === null || value === undefined ? '' : String(value);
    if (text.includes('"') || text.includes(',') || text.includes('\n') || text.includes('\r')) {
      return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
  }

  function handleExportTasksCsv() {
    if (!visibleTasks.length) {
      setActionMessage('暂无可导出的任务数据，请先查询或调整筛选条件。');
      return;
    }

    const headers = ['任务名称', '层级', '父任务ID', '业务类型', '任务性质', 'workday_costhour', '季度归属', '任务状态', '工时(天)', '链接'];
    const rows = visibleTasks.map((task) => {
      const taskId = String(task.taskId || '').trim();
      const depth = Number(visibleTaskDepthMap.get(taskId) || 0);
      const taskName = task.content || task.text || task.name || task.taskId || '-';
      const parentTaskId = String(task.parent_task_id || '').trim();
      const quarterCategory = (task.quarterCategory || '')
        .replace('当前季度排期', '当前季度')
        .replace('季度逾期排期', '季度逾期');
      const workHours = typeof task.work_hour === 'number' ? formatRawDays(task.work_hour) : formatRawDays(task.hours);
      const link = task.link || (task.taskId ? `https://www.teambition.com/task/${encodeURIComponent(task.taskId)}` : '');
      const wdRaw = task.workday_costhour;
      const wdNum = Number(wdRaw);
      const workdayCostHour = wdRaw === null || wdRaw === undefined || String(wdRaw).trim() === ''
        ? ''
        : (Number.isFinite(wdNum) ? String(wdNum) : String(wdRaw));
      return [taskName, depth, parentTaskId, task.type || '无', task.taskNature || '无', workdayCostHour, quarterCategory, task.status || '', workHours, link];
    });

    const csvLines = [headers, ...rows].map((row) => row.map(escapeCsvCell).join(','));
    const csvContent = `\uFEFF${csvLines.join('\n')}`;
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const now = new Date();
    const filename = `任务明细_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}.csv`;
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
    setActionMessage(`已导出 ${visibleTasks.length} 条任务明细。`);
  }

  return (
    <>
      <style>{`
        @keyframes drawCircle {
          from { stroke-dasharray: 0, 100; }
        }
        .chart-segment {
          animation: drawCircle 1s ease-out forwards;
        }
        .chart-segment:nth-child(2) { animation-delay: 0.15s; }
      `}</style>
      <EmployeeLayout>
      <SectionTitle
        title="工时管理"
        desc={canViewAllPeople
          ? ''
          : ''}
        right={(
          <div className="flex flex-wrap justify-end gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">
              最后同步：
              {' '}
              {lastUpdatedAt ? formatDateTime(lastUpdatedAt) : '暂无'}
            </div>
          </div>
        )}
      />
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">筛选条件</div>
          </div>
          <div className="flex flex-col items-start gap-3">
            <div className="flex items-start gap-2">
              <button
                type="button"
                onClick={() => handleQuery({
                  ...dateRange,
                  compensatoryDays,
                  target: selectedTarget,
                })}
                disabled={isQuerying}
                className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {isQuerying ? '查询中...' : '查询'}
              </button>
              <button
                type="button"
                onClick={handleUpdate}
                disabled={isUpdating}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60"
              >
                {isUpdating ? '同步中...' : '同步'}
              </button>
            </div>
          </div>
        </div>
        {canViewAllPeople ? (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <div className="grid grid-cols-[88px_180px_minmax(0,320px)] items-center gap-3">
              <div className="text-sm text-slate-500">查看对象</div>
              {memberGroupOptions.length ? (
                <>
                  <select
                    value={selectedTeam}
                    onChange={(event) => {
                      const nextTeam = event.target.value;
                      setSelectedTeam(nextTeam);
                      const firstMember = memberGroupOptions.find((group) => group.label === nextTeam)?.options?.[0];
                      if (firstMember) {
                        setSelectedTarget(String(firstMember.id));
                      }
                    }}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 outline-none"
                  >
                    {memberGroupOptions.map((group) => (
                      <option key={group.label} value={group.label}>
                        {group.label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selectedTarget}
                    onChange={(event) => setSelectedTarget(event.target.value)}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 outline-none"
                  >
                    {visibleTeamMembers.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                </>
              ) : (
                <select
                  value={selectedTarget}
                  onChange={(event) => setSelectedTarget(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 outline-none"
                >
                  {memberOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.team === '全部' ? option.name : `${option.name} · ${option.team}`}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
        ) : null}
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-center">
            <div className="flex w-full flex-wrap items-center gap-3">
              <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                <span className="shrink-0">开始时间</span>
                <input
                  type="datetime-local"
                  step="1"
                  value={dateRange.startDate}
                  onChange={(event) => handleDateChange('startDate', event.target.value)}
                  max={dateRange.endDate || undefined}
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none"
                />
              </label>
              <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
                <span className="shrink-0">结束时间</span>
                <input
                  type="datetime-local"
                  step="1"
                  value={dateRange.endDate}
                  onChange={(event) => handleDateChange('endDate', event.target.value)}
                  min={dateRange.startDate || undefined}
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none"
                />
              </label>
              <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  const nextRange = buildLastQuarterRange();
                  setQuickRangePreset('last_quarter');
                  setDateRange({
                    startDate: nextRange.startDate,
                    endDate: nextRange.endDate,
                  });
                  handleQuery(nextRange);
                }}
                disabled={isQuerying}
                className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium disabled:opacity-60 ${
                  quickRangePreset === 'last_quarter'
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                上季度
              </button>
              <button
                type="button"
                onClick={() => {
                  const nextRange = buildQuarterRange(false);
                  setQuickRangePreset('quarter');
                  setDateRange({
                    startDate: nextRange.startDate,
                    endDate: nextRange.endDate,
                  });
                  handleQuery(nextRange);
                }}
                disabled={isQuerying}
                className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium disabled:opacity-60 ${
                  quickRangePreset === 'quarter'
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                本季度
              </button>
              <button
                type="button"
                onClick={() => {
                  const nextRange = buildQuarterRange(true);
                  setQuickRangePreset('quarter_to_today');
                  setDateRange({
                    startDate: nextRange.startDate,
                    endDate: nextRange.endDate,
                  });
                  handleQuery(nextRange);
                }}
                disabled={isQuerying}
                className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium disabled:opacity-60 ${
                  quickRangePreset === 'quarter_to_today'
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                本季度至今天
              </button>
              </div>
            </div>
          </div>
        </div>
        {actionMessage ? (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
            {actionMessage}
          </div>
        ) : null}
      </Card>
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">工时数据总览</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">
            工作日天数 {formatRawDays(expectedWorkdayCount)}天
          </div>
        </div>
        <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-3">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 xl:col-span-2">
            <div className="text-sm text-slate-700">预期有效工时</div>
            <div className="mt-2 text-3xl font-semibold text-slate-900">{expectedEffectiveDays.toFixed(1)}天</div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="rounded-2xl border border-cyan-100 bg-cyan-50/50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-700">当前</div>
                <div className="space-y-3">
                  <StatCard title="当前已排总有效工时" value={`${formatRawDays(dashboard.scheduledEffectiveHours)}天`} sub="" valueAlign="right" />
                  <StatCard title="当前已完成总有效工时" value={`${formatRawDays(dashboard.completedEffectiveHours)}天`} sub="" valueAlign="right" />
                </div>
              </div>
              <div className="rounded-2xl border border-amber-100 bg-amber-50/50 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-700">季度逾期</div>
                <div className="space-y-3">
                  <StatCard title="季度逾期总有效工时" value={`${formatRawDays(dashboard.quarterlyOverdueEffectiveHours)}天`} sub="" valueAlign="right" />
                  <StatCard title="季度逾期完成工时" value={`${formatRawDays(dashboard.quarterlyOverdueCompletedHours)}天`} sub="" valueAlign="right" />
                </div>
              </div>
            </div>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white p-5 xl:col-span-1">
            <div className="text-base font-semibold text-slate-700">工作日耗时总览</div>
            <div className="mt-4 grid grid-cols-1 gap-4">
              <div className="min-h-[160px] rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-orange-700">总工作日</div>
                <div className="mt-3 flex min-h-[96px] items-center justify-end">
                  <div className="text-right text-3xl font-semibold text-slate-900">{formatRawDays(expectedWorkdayCount)}天</div>
                </div>
              </div>
              <div className="min-h-[160px] rounded-2xl border border-orange-100 bg-orange-50 p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-orange-700">已填工作日</div>
                <div className="mt-3 flex min-h-[96px] items-center justify-end">
                  <div className="text-right text-3xl font-semibold text-slate-900">{formatRawDays(filledWorkdayDays)}天</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="mt-5 rounded-3xl border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-4">
            <div className="text-lg font-semibold">工时情况</div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
              正值表示充足，负值表示不足
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div className={`rounded-2xl border p-4 ${scheduledStatus.bgClass}`}>
              <div className="text-sm text-slate-500">任务分配情况</div>
              <div className="mt-2 flex min-h-[72px] items-center justify-end">
                <div className={`text-right text-3xl font-semibold ${scheduledStatus.textClass}`}>
                  {scheduledStatus.sign}
                  {formatRawDays(scheduledDelta)}天
                </div>
              </div>
            </div>
            <div className={`rounded-2xl border p-4 ${completedStatus.bgClass}`}>
              <div className="text-sm text-slate-500">任务完成情况</div>
              <div className="mt-2 flex min-h-[72px] items-center justify-end">
                <div className={`text-right text-3xl font-semibold ${completedStatus.textClass}`}>
                  {completedStatus.sign}
                  {formatRawDays(completedDelta)}天
                </div>
              </div>
            </div>
            <div className={`rounded-2xl border p-4 ${workdayFilledStatus.bgClass}`}>
              <div className="text-sm text-slate-500">工作日耗时填写情况</div>
              <div className="mt-2 flex min-h-[72px] items-center justify-end">
                <div className={`text-right text-3xl font-semibold ${workdayFilledStatus.textClass}`}>
                  {workdayFilledStatus.sign}
                  {formatRawDays(workdayFilledDelta)}天
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
      <Card className="p-6">
        <div className="text-lg font-semibold">工时分布总览</div>
        <div className="mt-5 grid grid-cols-2 gap-5">
        <div className="flex h-full flex-col rounded-3xl border border-slate-200 bg-white p-6">
          <div className="text-lg font-semibold">季度已排任务分布</div>
          <div className="mt-5 grid flex-1 grid-cols-2 gap-5">
            <div className="flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-3 text-sm font-semibold text-slate-700">业务类型</div>
              <div className="flex flex-1 flex-col justify-between gap-4">
                {currentQuarterDistribution.map((item) => (
                  <div key={item.type} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="text-sm font-medium text-slate-900">{item.type}</div>
                      <div className="text-sm text-slate-500">
                        {formatRawDays(item.hours)}天
                        {' · '}
                        {item.ratio}
                      </div>
                    </div>
                    <div className="mt-3 h-3 rounded-full bg-slate-200">
                      <div
                        className={`h-3 rounded-full ${distributionBarClassMap[item.type]}`}
                        style={{ width: item.ratio }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-3 text-sm font-semibold text-slate-700">任务性质</div>
              <div className="flex flex-1 flex-col justify-between gap-4">
                {currentQuarterNatureDistribution.map((item) => (
                  <div key={item.nature} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="text-sm font-medium text-slate-900">{item.nature}</div>
                      <div className="text-sm text-slate-500">
                        {formatRawDays(item.hours)}天
                        {' · '}
                        {item.ratio}
                      </div>
                    </div>
                    <div className="mt-3 h-3 rounded-full bg-slate-200">
                      <div
                        className={`h-3 rounded-full ${taskNatureBarClassMap[item.nature]}`}
                        style={{ width: item.ratio }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
        <div className="flex h-full flex-col rounded-3xl border border-slate-200 bg-white p-6">
          <div className="text-lg font-semibold">月度数据</div>
          <div className="mt-5 flex-1 rounded-3xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 text-sm font-semibold text-slate-700">工时数据</div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-end justify-between gap-4">
                {trend.map((item) => {
                  const totalHeight = `${(item.total / maxTrendValue) * 160}px`;
                  const effectiveHeight = `${(item.effective / maxTrendValue) * 160}px`;
                  const completedHeight = `${(item.completed / maxTrendValue) * 160}px`;

                  return (
                    <div key={item.month} className="flex flex-1 flex-col items-center">
                      <div className="flex h-52 items-end gap-2">
                        <div className="flex flex-col items-center gap-2">
                          <div className="text-[11px] font-medium text-slate-500">{formatRawDays(item.total)}天</div>
                          <div
                            className="w-6 rounded-t-2xl bg-slate-300"
                            style={{ height: totalHeight }}
                            title={`${item.month} 预期有效工时 ${formatRawDays(item.total)}天`}
                          />
                        </div>
                        <div className="flex flex-col items-center gap-2">
                          <div className="text-[11px] font-medium text-cyan-700">{formatRawDays(item.effective)}天</div>
                          <div
                            className="w-6 rounded-t-2xl bg-cyan-500"
                            style={{ height: effectiveHeight }}
                            title={`${item.month} 已排有效工时 ${formatRawDays(item.effective)}天`}
                          />
                        </div>
                        <div className="flex flex-col items-center gap-2">
                          <div className="text-[11px] font-medium text-emerald-700">{formatRawDays(item.completed)}天</div>
                          <div
                            className="w-6 rounded-t-2xl bg-emerald-500"
                            style={{ height: completedHeight }}
                            title={`${item.month} 已完成有效工时 ${formatRawDays(item.completed)}天`}
                          />
                        </div>
                      </div>
                      <div className="mt-3 text-sm font-medium text-slate-700">{item.month}</div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex gap-4 text-xs text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-slate-300" />
                  <span>预期有效工时</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-cyan-500" />
                  <span>已排有效工时</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-emerald-500" />
                  <span>已完成有效工时</span>
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {trend.map((item) => (
                <div key={item.month} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="text-sm font-medium text-slate-900">{item.month}</div>
                    <div className="text-sm text-slate-500 text-center flex-1">
                      {(() => {
                        const total = Number(item.total || 0);
                        const effective = Number(item.effective || 0);
                        const scheduleRate = total > 0 ? `${Math.round((effective / total) * 100)}%` : '0%';
                        return `任务排布率 ${scheduleRate}`;
                      })()}
                    </div>
                    <div className="text-sm text-slate-500">
                      {(() => {
                        const effective = Number(item.effective || 0);
                        const completed = Number(item.completed || 0);
                        const completionRate = effective > 0 ? `${Math.round((completed / effective) * 100)}%` : '0%';
                        return `任务完成率 ${completionRate}`;
                      })()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-5">
          <div className="flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-4">
            <div className="text-sm font-semibold text-slate-700">软件开发 / 问题处理占比</div>
            <div className="mt-4 flex flex-1 flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-center gap-6">
                {/* SVG Donut */}
                <div className="relative w-36 h-36 shrink-0">
                  <svg viewBox="0 0 36 36" className="w-full h-full overflow-visible">
                    <path className="text-slate-200" strokeWidth="3.5" stroke="currentColor" fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                    {hourComposition.effectiveRatio > 0 && (
                      <path className="chart-segment"
                        strokeWidth="3.5" stroke="#1b9aee" fill="none"
                        strokeDasharray={`${hourComposition.effectiveRatio}, 100`}
                        strokeDashoffset="0"
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                    )}
                    {hourComposition.costRatio > 0 && (
                      <path className="chart-segment"
                        strokeWidth="3.5" stroke="#f97316" fill="none"
                        strokeDasharray={`${hourComposition.costRatio}, 100`}
                        strokeDashoffset={-hourComposition.effectiveRatio}
                        d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        style={{ animationDelay: '0.15s' }} />
                    )}
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-xl font-bold text-slate-800 leading-none">
                      {formatRawDays(hourComposition.effectiveHours + hourComposition.costHours).replace('天', '')}
                    </span>
                    <span className="text-[10px] text-slate-400 font-medium mt-0.5">人天</span>
                  </div>
                </div>
                {/* 图例 */}
                <div className="space-y-2 text-[12px] leading-4">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0 bg-[#1b9aee]" />
                    <span className="text-slate-500">软件开发</span>
                    <span className="font-semibold text-slate-800">{hourComposition.effectiveRatio}%</span>
                  </div>
                  <div className="text-[11px] text-slate-400 pl-[22px]">{formatRawDays(hourComposition.effectiveHours)}</div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0 bg-[#f97316]" />
                    <span className="text-slate-500">问题处理</span>
                    <span className="font-semibold text-slate-800">{hourComposition.costRatio}%</span>
                  </div>
                  <div className="text-[11px] text-slate-400 pl-[22px]">{formatRawDays(hourComposition.costHours)}</div>
                </div>
              </div>
            </div>
          </div>
          <div className="flex h-full flex-col rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-sm font-semibold text-slate-700">工作日耗时数据</div>
            <div className="mt-4 flex-1 rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-end justify-between gap-4">
                {monthlyWorkdayData.map((item) => {
                  const expectedHeight = `${(Number(item.expected || 0) / maxMonthlyWorkdayValue) * 140}px`;
                  const filledHeight = `${(Number(item.filled || 0) / maxMonthlyWorkdayValue) * 140}px`;
                  return (
                    <div key={item.month} className="flex flex-1 flex-col items-center">
                      <div className="flex h-44 items-end gap-2">
                        <div className="flex flex-col items-center gap-2">
                          <div className="text-[11px] font-medium text-slate-500">{formatRawDays(item.expected)}天</div>
                          <div
                            className="w-6 rounded-t-2xl bg-slate-300"
                            style={{ height: expectedHeight }}
                            title={`${item.month} 预期工作日 ${formatRawDays(item.expected)}天`}
                          />
                        </div>
                        <div className="flex flex-col items-center gap-2">
                          <div className="text-[11px] font-medium text-orange-700">{formatRawDays(item.filled)}天</div>
                          <div
                            className="w-6 rounded-t-2xl bg-orange-500"
                            style={{ height: filledHeight }}
                            title={`${item.month} 已填写工作日 ${formatRawDays(item.filled)}天`}
                          />
                        </div>
                      </div>
                      <div className="mt-2 text-sm font-medium text-slate-700">{item.month}</div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex gap-4 text-xs text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-slate-300" />
                  <span>预期工作日</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-orange-500" />
                  <span>已填写工作日</span>
                </div>
              </div>
            </div>
          </div>
      </div>
      </Card>
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">任务明细</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">
            当前季度排期 {currentQuarterTaskCount} 项
            {' · '}
            季度逾期排期 {overdueTaskCount} 项
            {' · '}
            已完成 {completedTaskCount} 项
            {' · '}
            未完成 {pendingTaskCount} 项
          </div>
        </div>
        <div className="mt-4 rounded-3xl border border-slate-200 bg-slate-50 p-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 space-y-4">
                <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-4 gap-y-3">
                  <div className="pt-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-900">类型</div>
                  <div className="flex flex-wrap gap-2">
                    {taskTypeOptions.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setTaskFilter(option)}
                        className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                          taskFilter === option
                            ? 'bg-slate-900 text-white shadow-sm'
                            : 'border border-slate-200 bg-slate-50 text-slate-700 hover:bg-white'
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                  <div className="pt-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-900">季度</div>
                  <div className="flex flex-wrap gap-2">
                    {quarterFilterOptions.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setQuarterFilter(option)}
                        className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                          quarterFilter === option
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'border border-slate-200 bg-slate-50 text-slate-700 hover:bg-white'
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                  <div className="pt-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-900">状态</div>
                  <div className="flex flex-wrap gap-2">
                    {statusFilterOptions.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setStatusFilter(option)}
                        className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                          statusFilter === option
                            ? 'bg-emerald-600 text-white shadow-sm'
                            : 'border border-slate-200 bg-slate-50 text-slate-700 hover:bg-white'
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4 xl:w-[420px]">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">查看控制</div>
                <div className="grid grid-cols-[minmax(0,132px)_56px_84px_84px] items-center gap-2">
                  <select
                    value={taskSort}
                    onChange={(event) => setTaskSort(event.target.value)}
                    className="min-w-0 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 outline-none"
                  >
                    <option value="desc">工时降序</option>
                    <option value="asc">工时升序</option>
                  </select>
                  <div className="text-center text-sm text-slate-500">
                    <span className="font-semibold text-slate-900">{filteredTasks.length}</span> 项
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowAllTasks((prev) => !prev)}
                    className="whitespace-nowrap rounded-2xl bg-slate-900 px-2 py-3 text-sm font-medium text-white hover:bg-slate-800"
                  >
                    {showAllTasks ? '收起' : '展开'}
                  </button>
                  <button
                    type="button"
                    onClick={resetTaskControls}
                    className="whitespace-nowrap rounded-2xl border border-slate-200 bg-white px-2 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    重置
                  </button>
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500">
                  {showAllTasks ? '已展示当前筛选下的全部任务' : '默认展示当前筛选下前 5 项'}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className={`mt-5 overflow-x-auto rounded-3xl border border-slate-200 ${showAllTasks ? '' : 'max-h-[320px] overflow-y-auto'}`}>
          <div className="sticky top-0 z-10 grid grid-cols-[minmax(0,1.54fr)_108px_108px_148px_108px_108px_108px_108px] gap-4 border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-medium text-slate-500">
            <div>任务名称</div>
            <div>业务类型</div>
            <div>任务性质</div>
            <div>季度归属</div>
            <div>任务状态</div>
            <div className="text-right">工作日耗时</div>
            <div className="text-right">有效工时</div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleExportTasksCsv}
                className="whitespace-nowrap rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100"
              >
                导出CSV
              </button>
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {visibleTasks.map((task) => (
              (() => {
                const taskId = String(task.taskId || '').trim();
                const parentId = String(task.parent_task_id || '').trim();
                const depth = Number(visibleTaskDepthMap.get(taskId) || 0);
                const isChildInCurrentList = Boolean(parentId) && visibleTaskIds.has(parentId) && depth > 0;
                const indentPx = Math.min(depth, 6) * 12;
                return (
              <div
                key={task.taskId || task.name}
                className="grid grid-cols-[minmax(0,1.54fr)_108px_108px_148px_108px_108px_108px_108px] items-center gap-4 bg-white px-5 py-4 text-sm transition-colors hover:bg-slate-50/70"
              >
                <div className="min-w-0 overflow-hidden" title={task.content || task.text || task.name || task.taskId || '-'}>
                  <div className="flex min-w-0 items-center">
                    {isChildInCurrentList ? (
                      <span
                        className="mr-2 shrink-0 text-slate-300"
                        style={{ paddingLeft: `${indentPx}px` }}
                        aria-hidden="true"
                      >
                        └
                      </span>
                    ) : null}
                    {(task.link || task.taskId) ? (
                      <a
                        href={task.link || `https://www.teambition.com/task/${encodeURIComponent(task.taskId)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="block min-w-0 flex-1 truncate font-medium text-sky-700 underline-offset-2 hover:underline"
                      >
                        {task.content || task.text || task.name || task.taskId || '-'}
                      </a>
                    ) : (
                      <div className="block min-w-0 flex-1 truncate font-medium text-slate-900">
                        {task.content || task.text || task.name || task.taskId || '-'}
                      </div>
                    )}
                  </div>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${taskTypeTagClassMap[task.type] || taskTypeTagClassMap.无}`}>
                    {task.type || '无'}
                  </span>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${taskNatureTagClassMap[task.taskNature] || taskNatureTagClassMap.无}`}>
                    {task.taskNature || '无'}
                  </span>
                </div>
                <div className="justify-self-start">
                  <span
                    className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${
                      quarterTagClassMap[(task.quarterCategory || '').replace('当前季度排期', '当前季度').replace('季度逾期排期', '季度逾期')]
                    }`}
                  >
                    {(task.quarterCategory || '').replace('当前季度排期', '当前季度').replace('季度逾期排期', '季度逾期')}
                  </span>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${statusTagClassMap[task.status]}`}>
                    {task.status}
                  </span>
                </div>
                <div className="text-right font-medium text-slate-700">
                  {task.workday_costhour === null || task.workday_costhour === undefined || String(task.workday_costhour).trim() === ''
                    ? '-'
                    : `${formatRawDays(task.workday_costhour)}天`}
                </div>
                <div className="text-right font-medium text-slate-700">
                  {typeof task.work_hour === 'number' ? formatRawDays(task.work_hour) : formatRawDays(task.hours)}天
                </div>
                <div />
              </div>
                );
              })()
            ))}
          </div>
        </div>
      </Card>
      {showBusyModal ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="busy-updating-title"
            className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-xl"
          >
            <h2 id="busy-updating-title" className="text-lg font-semibold text-slate-900">
              正在更新中
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              正在更新中，暂时无法查询
            </p>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setShowBusyModal(false)}
                className="rounded-2xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </EmployeeLayout>
    </>
  );
}
