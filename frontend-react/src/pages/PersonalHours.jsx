import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  fetchPersonalHoursMembers,
  queryPersonalHours,
  updatePersonalHours,
  fullUpdatePersonalHours,
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
  const [isFullUpdating, setIsFullUpdating] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const [showSyncActions, setShowSyncActions] = useState(false);
  const [showBusyModal, setShowBusyModal] = useState(false);
  const [quickRangePreset, setQuickRangePreset] = useState('quarter_to_today');
  const isAdmin = user?.role === ROLES.ADMIN;

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
        const nextMemberOptions = membersRes?.data?.memberOptions ?? [];
        const availableTargets = new Set(nextMemberOptions.map((item) => String(item?.id || '')));
        const targetFromUrl = String(defaultTarget || '').trim();
        const preferredTarget = availableTargets.has(targetFromUrl)
          ? targetFromUrl
          : (membersRes?.data?.selectedTarget ?? targetFromUrl);
        const nextTarget = availableTargets.has(String(preferredTarget || ''))
          ? String(preferredTarget || '')
          : (nextMemberOptions[0]?.id ?? defaultTarget);
        setMemberOptions(nextMemberOptions);
        // 先切换下拉选中，再发起工时查询，保证“跳转后先选人”。
        setSelectedTarget(nextTarget);
        const { payload, response } = await runInitialQuery(nextTarget);
        if (!active) return;
        setSourceTrend(response.data.trend ?? fallbackTrend);
        setDashboard(response.data.dashboard ?? fallbackDashboard);
        setDateRange({
          startDate: payload.startDate,
          endDate: payload.endDate,
        });
        setQuickRangePreset('quarter_to_today');
        setLastUpdatedAt((response.data.dashboard ?? {}).lastUpdatedAt ?? '');
        setCompensatoryDays((response.data.dashboard ?? {}).compensatoryDays ?? 0);
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
  const expectedEffectiveDays = expectedWorkdayCount * expectedCoefficient;
  const memberGroupOptions = useMemo(() => {
    if (!isAdmin) return [];
    const navMembers = memberOptions.filter((option) => option.team === '导航组');
    const integrationMembers = memberOptions.filter((option) => option.team === '对接组');
    const others = memberOptions.filter((option) => !['全部', '导航组', '对接组'].includes(String(option.team || '')));
    return [
      { label: '导航组', options: navMembers },
      { label: '对接组', options: integrationMembers },
      ...(others.length ? [{ label: '其他', options: others }] : []),
    ].filter((group) => group.options.length > 0);
  }, [isAdmin, memberOptions]);

  const scheduledDelta = dashboard.scheduledEffectiveHours + dashboard.quarterlyOverdueEffectiveHours - expectedEffectiveDays;
  const completedDelta = dashboard.completedEffectiveHours + dashboard.quarterlyOverdueCompletedHours - expectedEffectiveDays;
  const scheduledStatus = getDeltaStatus(scheduledDelta);
  const completedStatus = getDeltaStatus(completedDelta);
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
  };
  const quarterTagClassMap = {
    当前季度: 'border-sky-100 bg-sky-50 text-sky-700',
    季度逾期: 'border-amber-100 bg-amber-50 text-amber-700',
  };
  const statusTagClassMap = {
    创建中: 'border-yellow-200 bg-yellow-50 text-yellow-800',
    待评审: 'border-indigo-100 bg-indigo-50 text-indigo-700',
    评审中: 'border-blue-100 bg-blue-50 text-blue-700',
    搁置: 'border-amber-100 bg-amber-50 text-amber-700',
    已完成: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    未完成: 'border-rose-100 bg-rose-50 text-rose-700',
  };
  const taskTypeTagClassMap = {
    产品: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    订单: 'border-amber-100 bg-amber-50 text-amber-700',
    研发: 'border-violet-100 bg-violet-50 text-violet-700',
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

    return nextTasks;
  }, [dashboard.taskDetails, quarterFilter, showAllTasks, statusFilter, taskFilter, taskSort]);
  const visibleTasks = filteredTasks;
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

  function handleDateChange(field, value) {
    setQuickRangePreset('');
    setDateRange((prev) => {
      const next = {
        ...prev,
        [field]: value,
      };
      // 前端限制：终止时间不能早于起始时间
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
    if (payload?.startDate && payload?.endDate && payload.endDate < payload.startDate) {
      setActionMessage('终止时间不能早于起始时间。');
      return;
    }
    setIsQuerying(true);
    setActionMessage('');

    try {
      const response = await queryPersonalHours(user, payload);
      setSourceTrend(response.data.trend ?? fallbackTrend);
      setDashboard(response.data.dashboard);
      setLastUpdatedAt((current) => response.data.dashboard.lastUpdatedAt ?? current);
      setCompensatoryDays(response.data.dashboard.compensatoryDays ?? 0);
      setMemberOptions(response.data.memberOptions ?? memberOptions);
      const nextTarget = response.data.selectedTarget ?? payload.target ?? selectedTarget;
      setSelectedTarget(nextTarget);
      if (canViewAllPeople && nextTarget) {
        setSearchParams({ target: nextTarget });
      }
      setActionMessage(`已完成${response.data.dashboard.targetLabel ?? '当前对象'}的工时查询。`);
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
      const response = await updatePersonalHours(user, {
        ...dateRange,
        compensatoryDays,
        target: selectedTarget,
      });
      setLastUpdatedAt(response.data.lastUpdatedAt ?? lastUpdatedAt);
      setActionMessage(response.data.message || '已触发工时更新。');
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

  async function handleFullUpdate() {
    setIsFullUpdating(true);
    setActionMessage('');

    try {
      const response = await fullUpdatePersonalHours(user, {
        ...dateRange,
        compensatoryDays,
        target: selectedTarget,
        fullSync: true,
      });
      setLastUpdatedAt(response.data.lastUpdatedAt ?? lastUpdatedAt);
      setActionMessage(response.data.message || '已触发全量更新。');
      await handleQuery({
        ...dateRange,
        compensatoryDays,
        target: selectedTarget,
      });
    } catch (error) {
      if (isUpdateBusyError(error)) {
        showBusyHint();
        return;
      }
      setActionMessage(`全量更新失败：${error?.message || '未知错误'}`);
    } finally {
      setIsFullUpdating(false);
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
    if (!filteredTasks.length) {
      setActionMessage('暂无可导出的任务数据，请先查询或调整筛选条件。');
      return;
    }

    const headers = ['任务名称', '任务类型', '季度归属', '任务状态', '工时(天)', '链接'];
    const rows = filteredTasks.map((task) => {
      const taskName = task.content || task.text || task.name || task.taskId || '-';
      const quarterCategory = (task.quarterCategory || '')
        .replace('当前季度排期', '当前季度')
        .replace('季度逾期排期', '季度逾期');
      const workHours = typeof task.work_hour === 'number' ? formatRawDays(task.work_hour) : formatRawDays(task.hours);
      const link = task.link || (task.taskId ? `https://www.teambition.com/task/${encodeURIComponent(task.taskId)}` : '');
      return [taskName, task.type || '无', quarterCategory, task.status || '', workHours, link];
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
    setActionMessage(`已导出 ${filteredTasks.length} 条任务明细。`);
  }

  return (
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
            <div className="text-lg font-semibold">时间区间</div>
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
                onClick={() => setShowSyncActions((prev) => !prev)}
                disabled={isUpdating || isFullUpdating}
                aria-expanded={showSyncActions}
                aria-label={showSyncActions ? '收起同步' : '展开同步'}
                className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-medium disabled:opacity-60 ${
                  showSyncActions
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-700'
                }`}
              >
                <span>同步</span>
                <span className={`text-xs ${showSyncActions ? 'text-white' : 'text-slate-500'}`} aria-hidden="true">
                  {showSyncActions ? '◀' : '▶'}
                </span>
              </button>
              {showSyncActions ? (
                <>
                  <button
                    type="button"
                    onClick={handleUpdate}
                    disabled={isUpdating || isFullUpdating}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60"
                  >
                    {isUpdating ? '更新中...' : '更新'}
                  </button>
                  <button
                    type="button"
                    onClick={handleFullUpdate}
                    disabled={isFullUpdating || isUpdating}
                    className="whitespace-nowrap rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-60"
                  >
                    {isFullUpdating ? '全量更新中...' : '全量更新'}
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </div>
        {canViewAllPeople ? (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <div className="grid grid-cols-[88px_minmax(0,320px)] items-center gap-3">
              <div className="text-sm text-slate-500">查看对象</div>
              <select
                value={selectedTarget}
                onChange={(event) => setSelectedTarget(event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 outline-none"
              >
                {isAdmin ? (
                  memberGroupOptions.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.options.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.name}
                        </option>
                      ))}
                    </optgroup>
                  ))
                ) : (
                  memberOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.team === '全部' ? option.name : `${option.name} · ${option.team}`}
                    </option>
                  ))
                )}
              </select>
            </div>
          </div>
        ) : null}
        <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid grid-cols-[88px_minmax(0,1fr)_88px_minmax(0,1fr)_auto_1fr_88px_120px] items-center gap-3">
            <div className="text-sm text-slate-500">起始时间</div>
            <input
              type="datetime-local"
              step="1"
              value={dateRange.startDate}
              onChange={(event) => handleDateChange('startDate', event.target.value)}
              max={dateRange.endDate || undefined}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            />
            <div className="text-sm text-slate-500">终止时间</div>
            <input
              type="datetime-local"
              step="1"
              value={dateRange.endDate}
              onChange={(event) => handleDateChange('endDate', event.target.value)}
              min={dateRange.startDate || undefined}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            />
            <div className="flex flex-nowrap gap-2">
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
            <div />
            <div className="text-sm text-right text-slate-500">调休天数</div>
            <div className="flex items-center rounded-2xl border border-slate-200 bg-white">
              <input
                type="number"
                min="0"
                step="0.5"
                value={compensatoryDays}
                onChange={(event) => setCompensatoryDays(event.target.value)}
                className="w-full rounded-l-2xl bg-white px-4 py-3 text-sm text-slate-700 outline-none"
              />
              <div className="rounded-r-2xl border-l border-slate-200 px-4 py-3 text-sm text-slate-500">天</div>
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
            当前区间共 {expectedWorkdayCount.toFixed(1)} 个工作日
          </div>
        </div>
        <div className="mt-5 grid grid-cols-12 gap-5">
          <Card className="col-span-5 row-span-2 flex flex-col justify-between p-6">
            <div>
              <div className="text-sm text-slate-500">预期有效工时</div>
              <div className="mt-3 text-4xl font-semibold text-slate-900">{expectedEffectiveDays.toFixed(1)}天</div>
            </div>
          </Card>
          <div className="col-span-7 grid grid-cols-2 gap-5">
            <StatCard title="当前已排总有效工时" value={`${formatRawDays(dashboard.scheduledEffectiveHours)}天`} sub="" />
            <StatCard title="当前已完成总有效工时" value={`${formatRawDays(dashboard.completedEffectiveHours)}天`} sub="" />
            <StatCard title="季度逾期总有效工时" value={`${formatRawDays(dashboard.quarterlyOverdueEffectiveHours)}天`} sub="" />
            <StatCard title="季度逾期完成工时" value={`${formatRawDays(dashboard.quarterlyOverdueCompletedHours)}天`} sub="" />
          </div>
        </div>
        <div className="mt-6 border-t border-slate-200 pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">工时情况</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
              正值表示充足，负值表示不足
            </div>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-5">
            <div className={`rounded-2xl border p-5 ${scheduledStatus.bgClass}`}>
              <div className="flex items-center justify-between gap-4">
                <div className="text-sm text-slate-500">任务分配情况</div>
                <div className={`text-right text-4xl font-semibold ${scheduledStatus.textClass}`}>
                  {scheduledStatus.sign}
                  {formatRawDays(scheduledDelta)}天
                </div>
              </div>
            </div>
            <div className={`rounded-2xl border p-5 ${completedStatus.bgClass}`}>
              <div className="flex items-center justify-between gap-4">
                <div className="text-sm text-slate-500">任务完成情况</div>
                <div className={`text-right text-4xl font-semibold ${completedStatus.textClass}`}>
                  {completedStatus.sign}
                  {formatRawDays(completedDelta)}天
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-6">
          <div className="text-lg font-semibold">季度已排任务分布</div>
          <div className="mt-5 space-y-4">
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
        </Card>
        <Card className="p-6">
          <div className="text-lg font-semibold">月度趋势</div>
          <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-5">
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
          <div className="mt-5 space-y-3">
            {trend.map((item) => (
              <div key={item.month} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm font-medium text-slate-900">{item.month}</div>
                  <div className="text-sm text-slate-500">任务完成率 {item.completionRate}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
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
              <div className="w-[420px] rounded-2xl border border-slate-200 bg-slate-50 p-4">
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
        <div className={`mt-5 rounded-3xl border border-slate-200 ${showAllTasks ? '' : 'max-h-[320px] overflow-auto'}`}>
          <div className="sticky top-0 z-10 grid grid-cols-[minmax(0,1.82fr)_108px_148px_108px_108px_108px] gap-6 border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-medium text-slate-500">
            <div>任务名称</div>
            <div>任务类型</div>
            <div>季度归属</div>
            <div>任务状态</div>
            <div className="text-right">工时</div>
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
              <div
                key={task.taskId || task.name}
                className="grid grid-cols-[minmax(0,1.82fr)_108px_148px_108px_108px_108px] items-center gap-6 bg-white px-5 py-4 text-sm transition-colors hover:bg-slate-50/70"
              >
                <div className="min-w-0" title={task.content || task.text || task.name || task.taskId || '-'}>
                  {(task.link || task.taskId) ? (
                    <a
                      href={task.link || `https://www.teambition.com/task/${encodeURIComponent(task.taskId)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate font-medium text-sky-700 underline-offset-2 hover:underline"
                    >
                      {task.content || task.text || task.name || task.taskId || '-'}
                    </a>
                  ) : (
                    <div className="truncate font-medium text-slate-900">{task.content || task.text || task.name || task.taskId || '-'}</div>
                  )}
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${taskTypeTagClassMap[task.type] || taskTypeTagClassMap.无}`}>
                    {task.type || '无'}
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
                  {typeof task.work_hour === 'number' ? formatRawDays(task.work_hour) : formatRawDays(task.hours)}天
                </div>
                <div />
              </div>
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
  );
}
