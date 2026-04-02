import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchPersonalHours, queryPersonalHours, updatePersonalHours } from '../api/dashboard';
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
  calculateExpectedEffectiveDays,
  formatDateTime,
  formatDays,
  getDeltaStatus,
} from '../utils/workHours';
import { useAuthStore } from '../store/authStore';

export default function PersonalHours() {
  const user = useAuthStore((state) => state.user);
  const canViewAllPeople = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const [searchParams, setSearchParams] = useSearchParams();
  const targetFromQuery = searchParams.get('target') ?? '';
  const defaultTarget = canViewAllPeople ? (targetFromQuery || 'ALL') : user?.name ?? '';
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

  useEffect(() => {
    let active = true;

    fetchPersonalHours(user, { target: defaultTarget }).then((response) => {
      if (active) {
        setSourceTrend(response.data.trend ?? fallbackTrend);
        setDashboard(response.data.dashboard);
        setDateRange(response.data.dashboard.defaultRange);
        setLastUpdatedAt(response.data.dashboard.lastUpdatedAt ?? '');
        setCompensatoryDays(response.data.dashboard.compensatoryDays ?? 0);
        setMemberOptions(response.data.memberOptions ?? []);
        setSelectedTarget(response.data.selectedTarget ?? defaultTarget);
      }
    });

    return () => {
      active = false;
    };
  }, [defaultTarget, user]);

  const expectedSummary = useMemo(
    () => calculateExpectedEffectiveDays(
      dateRange.startDate,
      dateRange.endDate,
      dashboard.statutoryHolidays,
      compensatoryDays,
    ),
    [compensatoryDays, dashboard.statutoryHolidays, dateRange.endDate, dateRange.startDate],
  );

  const scheduledDelta = dashboard.scheduledEffectiveHours + dashboard.quarterlyOverdueEffectiveHours - expectedSummary.hours;
  const completedDelta = dashboard.completedEffectiveHours + dashboard.quarterlyOverdueCompletedHours - expectedSummary.hours;
  const scheduledStatus = getDeltaStatus(scheduledDelta);
  const completedStatus = getDeltaStatus(completedDelta);
  const trend = useMemo(() => buildMonthlyTrend(sourceTrend, dashboard.taskDetails), [dashboard.taskDetails, sourceTrend]);
  const maxTrendValue = Math.max(...trend.flatMap((item) => [item.total, item.effective, item.completed]), 1);
  const distributionBarClassMap = {
    产品: 'bg-sky-500',
    订单: 'bg-amber-500',
    研发: 'bg-emerald-500',
  };
  const quarterTagClassMap = {
    当前季度排期: 'border-sky-100 bg-sky-50 text-sky-700',
    季度逾期排期: 'border-amber-100 bg-amber-50 text-amber-700',
  };
  const statusTagClassMap = {
    已完成: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    未完成: 'border-rose-100 bg-rose-50 text-rose-700',
  };
  const taskTypeTagClassMap = {
    产品: 'border-violet-100 bg-violet-50 text-violet-700',
    订单: 'border-amber-100 bg-amber-50 text-amber-700',
    研发: 'border-cyan-100 bg-cyan-50 text-cyan-700',
  };
  const taskTypeOptions = ['全部', '产品', '订单', '研发'];
  const quarterFilterOptions = ['全部', '当前季度排期', '季度逾期排期'];
  const statusFilterOptions = ['全部', '已完成', '未完成'];
  const filteredTasks = useMemo(() => {
    const nextTasks = dashboard.taskDetails
      .filter((task) => taskFilter === '全部' || task.type === taskFilter)
      .filter((task) => quarterFilter === '全部' || task.quarterCategory === quarterFilter)
      .filter((task) => statusFilter === '全部' || task.status === statusFilter)
      .sort((left, right) => (taskSort === 'desc' ? right.hours - left.hours : left.hours - right.hours));

    return showAllTasks ? nextTasks : nextTasks.slice(0, 5);
  }, [dashboard.taskDetails, quarterFilter, showAllTasks, statusFilter, taskFilter, taskSort]);
  const overdueTaskCount = dashboard.taskDetails.filter((task) => task.quarterCategory === '季度逾期排期').length;
  const currentQuarterTaskCount = dashboard.taskDetails.filter((task) => task.quarterCategory === '当前季度排期').length;
  const completedTaskCount = dashboard.taskDetails.filter((task) => task.status === '已完成').length;
  const pendingTaskCount = dashboard.taskDetails.filter((task) => task.status === '未完成').length;
  const currentQuarterDistribution = useMemo(() => {
    const currentQuarterTasks = dashboard.taskDetails.filter((task) => task.quarterCategory === '当前季度排期');
    const totalHours = currentQuarterTasks.reduce((sum, task) => sum + task.hours, 0);

    return ['产品', '订单', '研发'].map((type) => {
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
    setDateRange((prev) => ({
      ...prev,
      [field]: value,
    }));
  }

  function resetTaskControls() {
    setTaskFilter('全部');
    setQuarterFilter('全部');
    setStatusFilter('全部');
    setTaskSort('desc');
    setShowAllTasks(false);
  }

  async function handleQuery(payload = { ...dateRange, compensatoryDays }) {
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
    } finally {
      setIsUpdating(false);
    }
  }

  return (
    <EmployeeLayout>
      <SectionTitle
        title="工时管理"
        desc="员工端只展示本人数据，页面聚焦个人工时达成、趋势与任务分布。"
        right={(
          <div className="flex gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">个人账号已登录</div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">仅本人可见</div>
          </div>
        )}
      />
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">时间区间</div>
            <div className="mt-1 text-sm text-slate-500">支持输入起始时间和终止时间，结合法定节假日计算预期有效工时。</div>
          </div>
          <div className="flex flex-col items-end gap-3">
            <div className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500">
              最后更新时间：
              {' '}
              <span className="font-medium text-slate-700">{lastUpdatedAt ? formatDateTime(lastUpdatedAt) : '暂无'}</span>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  const nextRange = buildQuarterRange(false);
                  setDateRange({
                    startDate: nextRange.startDate,
                    endDate: nextRange.endDate,
                  });
                  handleQuery(nextRange);
                }}
                disabled={isQuerying}
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                本季度
              </button>
              <button
                type="button"
                onClick={() => {
                  const nextRange = buildQuarterRange(true);
                  setDateRange({
                    startDate: nextRange.startDate,
                    endDate: nextRange.endDate,
                  });
                  handleQuery(nextRange);
                }}
                disabled={isQuerying}
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                本季度至今天
              </button>
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
                {isUpdating ? '更新中...' : '更新'}
              </button>
            </div>
            <div className="flex flex-wrap justify-end gap-4 text-xs text-slate-500">
              <div>查询：按当前时间区间刷新页面统计结果</div>
              <div>更新：触发后台同步并刷新最后更新时间</div>
            </div>
          </div>
        </div>
        {canViewAllPeople ? (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4">
            <div className="grid grid-cols-[88px_minmax(0,320px)_1fr] items-center gap-3">
              <div className="text-sm text-slate-500">查看对象</div>
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
              <div className="text-sm text-slate-500">
                当前查看：
                {' '}
                <span className="font-medium text-slate-700">{dashboard.targetLabel ?? '全部人员'}</span>
              </div>
            </div>
          </div>
        ) : null}
        <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid grid-cols-[88px_minmax(0,1fr)_88px_minmax(0,1fr)_1fr_88px_120px] items-center gap-3">
            <div className="text-sm text-slate-500">起始时间</div>
            <input
              type="datetime-local"
              step="1"
              value={dateRange.startDate}
              onChange={(event) => handleDateChange('startDate', event.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            />
            <div className="text-sm text-slate-500">终止时间</div>
            <input
              type="datetime-local"
              step="1"
              value={dateRange.endDate}
              onChange={(event) => handleDateChange('endDate', event.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            />
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
            <div className="mt-1 text-sm text-slate-500">先看当前区间的工时概览，再看排期和完成进度相对预期的差值分析。</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">
            当前区间共 {expectedSummary.days.toFixed(1)} 个有效工天
          </div>
        </div>
        <div className="mt-5 grid grid-cols-12 gap-5">
          <Card className="col-span-5 row-span-2 flex flex-col justify-between p-6">
            <div>
              <div className="text-sm text-slate-500">预期有效工时</div>
              <div className="mt-3 text-4xl font-semibold text-slate-900">{expectedSummary.days.toFixed(1)}天</div>
              <div className="mt-3 text-sm leading-7 text-slate-500">
                依据起始时间、终止时间、法定节假日与双休日综合计算后，再扣减调休天数，得到当前区间的有效工天。
              </div>
            </div>
            <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">计算说明</div>
              <div className="mt-2 text-sm leading-6 text-slate-600">
                法定节假日 {expectedSummary.holidayCount} 天，调休天数 {expectedSummary.compensatoryDays.toFixed(1)} 天，折合 {formatDays(expectedSummary.hours)}天，可作为排期与完成情况的对比基线。
              </div>
            </div>
          </Card>
          <div className="col-span-7 grid grid-cols-2 gap-5">
            <StatCard title="当前已排总有效工时" value={`${formatDays(dashboard.scheduledEffectiveHours)}天`} sub="已纳入当前区间任务排期" />
            <StatCard title="当前已完成总有效工时" value={`${formatDays(dashboard.completedEffectiveHours)}天`} sub="已完成任务的累计有效工时" />
            <StatCard title="季度逾期总有效工时" value={`${formatDays(dashboard.quarterlyOverdueEffectiveHours)}天`} sub="跨季度未按期关闭任务累计" />
            <StatCard title="季度逾期完成工时" value={`${formatDays(dashboard.quarterlyOverdueCompletedHours)}天`} sub="跨季度已完成关闭任务累计" />
          </div>
        </div>
        <div className="mt-6 border-t border-slate-200 pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">工时情况</div>
              <div className="mt-1 text-sm text-slate-500">对比预期有效工时与排期 / 完成进度，快速识别是否偏紧或偏松。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
              正值表示充足，负值表示不足
            </div>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-5">
            <div className={`rounded-2xl border p-5 ${scheduledStatus.bgClass}`}>
              <div className="text-sm text-slate-500">任务分配情况</div>
              <div className={`mt-2 text-2xl font-semibold ${scheduledStatus.textClass}`}>
                {scheduledStatus.sign}
                {formatDays(scheduledDelta)}天
              </div>
              <div className="mt-2 text-sm text-slate-600">
                (当前已排总有效工时 + 季度逾期总有效工时) - 预期有效工时 = {formatDays(dashboard.scheduledEffectiveHours + dashboard.quarterlyOverdueEffectiveHours)}天 - {expectedSummary.days.toFixed(1)}天
              </div>
            </div>
            <div className={`rounded-2xl border p-5 ${completedStatus.bgClass}`}>
              <div className="text-sm text-slate-500">任务完成情况</div>
              <div className={`mt-2 text-2xl font-semibold ${completedStatus.textClass}`}>
                {completedStatus.sign}
                {formatDays(completedDelta)}天
              </div>
              <div className="mt-2 text-sm text-slate-600">
                (已完成有效工时 + 季度逾期完成工时) - 预期有效工时 = {formatDays(dashboard.completedEffectiveHours + dashboard.quarterlyOverdueCompletedHours)}天 - {expectedSummary.days.toFixed(1)}天
              </div>
            </div>
          </div>
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-6">
          <div className="text-lg font-semibold">季度已排任务分布</div>
          <div className="mt-1 text-sm text-slate-500">当前数据口径仅统计“当前季度排期”的任务，不包含“季度逾期排期”任务，按产品、订单、研发三类展示结构占比。</div>
          <div className="mt-5 space-y-4">
            {currentQuarterDistribution.map((item) => (
              <div key={item.type} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm font-medium text-slate-900">{item.type}</div>
                  <div className="text-sm text-slate-500">
                    {formatDays(item.hours)}天
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
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
            统计口径：仅包含当前季度排期任务，不包含季度逾期排期任务，也不区分已完成与未完成。
          </div>
        </Card>
        <Card className="p-6">
          <div className="text-lg font-semibold">月度趋势</div>
          <div className="mt-1 text-sm text-slate-500">柱状图展示每月总工时、有效工时和已完成工时，下面只保留完成率。</div>
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
                        <div className="text-[11px] font-medium text-slate-500">{formatDays(item.total)}天</div>
                        <div
                          className="w-6 rounded-t-2xl bg-slate-300"
                          style={{ height: totalHeight }}
                          title={`${item.month} 总工时 ${formatDays(item.total)}天`}
                        />
                      </div>
                      <div className="flex flex-col items-center gap-2">
                        <div className="text-[11px] font-medium text-cyan-700">{formatDays(item.effective)}天</div>
                        <div
                          className="w-6 rounded-t-2xl bg-cyan-500"
                          style={{ height: effectiveHeight }}
                          title={`${item.month} 有效工时 ${formatDays(item.effective)}天`}
                        />
                      </div>
                      <div className="flex flex-col items-center gap-2">
                        <div className="text-[11px] font-medium text-emerald-700">{formatDays(item.completed)}天</div>
                        <div
                          className="w-6 rounded-t-2xl bg-emerald-500"
                          style={{ height: completedHeight }}
                          title={`${item.month} 已完成工时 ${formatDays(item.completed)}天`}
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
                <span>总工天</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-cyan-500" />
                <span>有效工天</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-emerald-500" />
                <span>已完成工天</span>
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
            <div className="mt-1 text-sm text-slate-500">以紧凑表格展示任务名称、类型、季度归属、工天与 Teambition 链接。</div>
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
        <div className="mt-5 max-h-[420px] overflow-auto rounded-3xl border border-slate-200">
          <div className="sticky top-0 z-10 grid grid-cols-[minmax(0,1.82fr)_108px_148px_108px_108px_176px] gap-8 border-b border-slate-200 bg-slate-50 px-5 py-4 text-sm font-medium text-slate-500">
            <div>任务名称</div>
            <div>任务类型</div>
            <div>季度归属</div>
            <div>状态</div>
            <div className="text-right">工时</div>
            <div>链接</div>
          </div>
          <div className="divide-y divide-slate-100">
            {filteredTasks.map((task) => (
              <div
                key={task.name}
                className="grid grid-cols-[minmax(0,1.82fr)_108px_148px_108px_108px_176px] items-center gap-8 bg-white px-5 py-4 text-sm transition-colors hover:bg-slate-50/70"
              >
                <div className="min-w-0" title={task.name}>
                  <div className="truncate font-medium text-slate-900">{task.name}</div>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${taskTypeTagClassMap[task.type]}`}>
                    {task.type}
                  </span>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${quarterTagClassMap[task.quarterCategory]}`}>
                    {task.quarterCategory}
                  </span>
                </div>
                <div className="justify-self-start">
                  <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${statusTagClassMap[task.status]}`}>
                    {task.status}
                  </span>
                </div>
                <div className="text-right font-medium text-slate-700">{formatDays(task.hours)}天</div>
                <div>
                  <a
                    href={task.link}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                  >
                    查看任务
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </EmployeeLayout>
  );
}
