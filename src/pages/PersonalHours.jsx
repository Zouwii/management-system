import { useEffect, useMemo, useState } from 'react';
import { fetchPersonalHours, queryPersonalHours, updatePersonalHours } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import EmployeeLayout from '../layouts/EmployeeLayout';
import {
  personalHours as fallbackTrend,
  personalHoursDashboard as fallbackDashboard,
} from '../mock/platformData';
import {
  calculateExpectedEffectiveDays,
  formatDateTime,
  formatDays,
  getDeltaStatus,
} from '../utils/workHours';

export default function PersonalHours() {
  const [trend, setTrend] = useState(fallbackTrend);
  const [dashboard, setDashboard] = useState(fallbackDashboard);
  const [dateRange, setDateRange] = useState(fallbackDashboard.defaultRange);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [actionMessage, setActionMessage] = useState('');

  useEffect(() => {
    let active = true;

    fetchPersonalHours().then((response) => {
      if (active) {
        setTrend(response.data.trend);
        setDashboard(response.data.dashboard);
        setDateRange(response.data.dashboard.defaultRange);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  const expectedSummary = useMemo(
    () => calculateExpectedEffectiveDays(
      dateRange.startDate,
      dateRange.endDate,
      dashboard.statutoryHolidays,
    ),
    [dashboard.statutoryHolidays, dateRange.endDate, dateRange.startDate],
  );

  const scheduledDelta = dashboard.scheduledEffectiveHours + dashboard.quarterlyPlannedEffectiveHours - expectedSummary.hours;
  const completedDelta = dashboard.completedEffectiveHours + dashboard.quarterlyPlannedCompletedHours - expectedSummary.hours;
  const scheduledStatus = getDeltaStatus(scheduledDelta);
  const completedStatus = getDeltaStatus(completedDelta);
  const visibleTasks = showAllTasks ? dashboard.taskDetails : dashboard.taskDetails.slice(0, 5);

  function handleDateChange(field, value) {
    setDateRange((prev) => ({
      ...prev,
      [field]: value,
    }));
  }

  async function handleQuery() {
    setIsQuerying(true);
    setActionMessage('');

    try {
      const response = await queryPersonalHours(dateRange);
      setTrend(response.data.trend);
      setDashboard(response.data.dashboard);
      setActionMessage('已完成当前时间区间的工时查询。');
    } finally {
      setIsQuerying(false);
    }
  }

  async function handleUpdate() {
    setIsUpdating(true);
    setActionMessage('');

    try {
      const response = await updatePersonalHours(dateRange);
      setActionMessage(response.data.message || '已触发工时更新。');
    } finally {
      setIsUpdating(false);
    }
  }

  return (
    <EmployeeLayout>
      <SectionTitle
        title="个人工时管理"
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
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleQuery}
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
        </div>
        <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid grid-cols-[88px_minmax(0,320px)_88px_minmax(0,320px)] items-center gap-3">
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
          </div>
        </div>
        <div className="mt-4 text-sm leading-6 text-slate-500">
          当前区间：
          {' '}
          {formatDateTime(dateRange.startDate)}
          {' 至 '}
          {formatDateTime(dateRange.endDate)}
          {' · '}
          已纳入计算的法定节假日：
          {' '}
          {dashboard.statutoryHolidays.map((item) => `${item.name}（${item.date}）`).join(' / ')}
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
        <div className="mt-5 grid grid-cols-5 gap-5">
          <StatCard title="预期有效工时" value={`${expectedSummary.days.toFixed(1)}天`} sub={`法定节假日 ${expectedSummary.holidayCount} 天，折合 ${expectedSummary.hours}h`} />
          <StatCard title="当前已排总有效工时" value={`${formatDays(dashboard.scheduledEffectiveHours)}天`} sub="已纳入当前区间任务排期" />
          <StatCard title="当前已完成总有效工时" value={`${formatDays(dashboard.completedEffectiveHours)}天`} sub="已完成任务的累计有效工时" />
          <StatCard title="季度预期完成工时" value={`${formatDays(dashboard.quarterlyPlannedCompletedHours)}天`} sub="本季度计划完成任务的有效工时" />
          <StatCard title="季度逾期总有效工时" value={`${formatDays(dashboard.quarterlyOverdueEffectiveHours)}天`} sub="跨季度未按期关闭任务累计" />
        </div>
        <div className="mt-6 border-t border-slate-200 pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-lg font-semibold">工时情况</div>
              <div className="mt-1 text-sm text-slate-500">对比预期有效工时与排期 / 完成进度，快速识别是否偏紧或偏松。</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500">
              负值表示偏紧，正值表示有余量
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
                预期有效工时 vs (当前已排总有效工时 + 季度预期工时) = {expectedSummary.days.toFixed(1)}天 vs {formatDays(dashboard.scheduledEffectiveHours + dashboard.quarterlyPlannedEffectiveHours)}天
              </div>
            </div>
            <div className={`rounded-2xl border p-5 ${completedStatus.bgClass}`}>
              <div className="text-sm text-slate-500">任务完成情况</div>
              <div className={`mt-2 text-2xl font-semibold ${completedStatus.textClass}`}>
                {completedStatus.sign}
                {formatDays(completedDelta)}天
              </div>
              <div className="mt-2 text-sm text-slate-600">
                预期有效工时 vs (已完成有效工时 + 季度预期完成工时) = {expectedSummary.days.toFixed(1)}天 vs {formatDays(dashboard.completedEffectiveHours + dashboard.quarterlyPlannedCompletedHours)}天
              </div>
            </div>
          </div>
        </div>
      </Card>
      <Card className="p-6">
        <div className="text-lg font-semibold">任务分布</div>
        <div className="mt-1 text-sm text-slate-500">当前任务类型分为产品、订单、研发三类。</div>
        <div className="mt-5 grid grid-cols-3 gap-4 text-sm">
          {dashboard.taskDistribution.map((item) => (
            <div key={item.type} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-slate-500">{item.type}</div>
              <div className="mt-2 text-2xl font-semibold text-slate-900">{formatDays(item.hours)}天</div>
              <div className="mt-2 text-sm text-slate-500">占比 {item.ratio}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-6">
        <div className="text-lg font-semibold">月度趋势</div>
        <div className="mt-1 text-sm text-slate-500">展示本人近三个月总工时、有效工时和任务结构变化。</div>
        <div className="mt-5 grid grid-cols-3 gap-4">
          {trend.map((item) => (
            <div key={item.month} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm text-slate-500">{item.month}</div>
              <div className="mt-2 text-2xl font-semibold">{formatDays(item.effective)}天</div>
              <div className="mt-2 text-sm text-slate-500">总工时 {formatDays(item.total)}天</div>
              <div className="mt-1 text-sm text-slate-500">有效率 {item.efficiency}</div>
              <div className="mt-3 text-xs leading-5 text-slate-500">{item.taskType}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-6">
        <div className="text-lg font-semibold">本月任务分布</div>
        <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">产品任务：29%</div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">订单任务：27%</div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">研发任务：44%</div>
        </div>
      </Card>
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">任务明细</div>
            <div className="mt-1 text-sm text-slate-500">展示任务名称与工时，支持折叠和跳转到 Teambition。</div>
          </div>
          <button
            type="button"
            onClick={() => setShowAllTasks((prev) => !prev)}
            className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {showAllTasks ? '收起任务' : '展开全部任务'}
          </button>
        </div>
        <div className="mt-5 space-y-3">
          {visibleTasks.map((task) => (
            <div key={task.name} className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div>
                <div className="text-sm font-medium text-slate-900">{task.name}</div>
                <div className="mt-1 text-sm text-slate-500">
                  类型：{task.type}
                  {' · '}
                  工时：{formatDays(task.hours)}天
                </div>
              </div>
              <a
                href={task.link}
                target="_blank"
                rel="noreferrer"
                className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                查看任务
              </a>
            </div>
          ))}
        </div>
      </Card>
    </EmployeeLayout>
  );
}
