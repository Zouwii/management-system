import { countWorkdays } from 'chinese-workday';

const HOURS_PER_DAY = 8;

function toDate(dateString) {
  const normalized = dateString.includes('T') ? dateString : `${dateString}T00:00:00`;
  return new Date(normalized);
}

function toLocalYmd(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function calculateExpectedEffectiveDays(startDate, endDate, holidays = [], compensatoryDays = 0) {
  if (!startDate || !endDate || startDate > endDate) {
    return {
      days: 0,
      hours: 0,
      holidayCount: 0,
      compensatoryDays: 0,
    };
  }

  const holidaySet = new Set(holidays.map((item) => item.date));
  const start = toDate(startDate);
  const end = toDate(endDate);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return {
      days: 0,
      hours: 0,
      holidayCount: 0,
      compensatoryDays: Number(compensatoryDays || 0),
    };
  }

  // 必须使用“本地日历日期”，不能用 toISOString()（会触发时区回退导致多/少一天）。
  const startYmd = toLocalYmd(start);
  const endYmd = toLocalYmd(end);

  let workdays = 0;
  try {
    // 对齐 Vue 旧口径：使用 chinese-workday（含法定节假日与调休补班）。
    workdays = Number(countWorkdays(startYmd, endYmd) || 0);
  } catch (e) {
    workdays = 0;
  }

  const totalDays = Math.floor((new Date(
    end.getFullYear(),
    end.getMonth(),
    end.getDate(),
  ) - new Date(
    start.getFullYear(),
    start.getMonth(),
    start.getDate(),
  )) / 86400000) + 1;
  // 若前端有显式 holiday 列表，优先展示其数量；否则按“总天数-法定工作日”估算。
  const holidayCount = holidaySet.size > 0 ? holidaySet.size : Math.max(0, totalDays - workdays);

  const adjustedDays = Math.max(workdays - Number(compensatoryDays || 0), 0);

  return {
    days: adjustedDays,
    hours: adjustedDays * HOURS_PER_DAY,
    holidayCount,
    compensatoryDays: Number(compensatoryDays || 0),
  };
}

export function getDeltaStatus(value) {
  if (value < 0) {
    return {
      textClass: 'text-rose-700',
      bgClass: 'bg-rose-50 border-rose-100',
      sign: '',
    };
  }

  return {
    textClass: 'text-emerald-700',
    bgClass: 'bg-emerald-50 border-emerald-100',
    sign: '+',
  };
}

export function formatDays(hours) {
  return (hours / HOURS_PER_DAY).toFixed(1);
}

export function formatDateTime(value) {
  if (!value) {
    return '';
  }

  const normalized = value.length === 16 ? `${value}:00` : value;
  const hasExplicitTimezone = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized);
  const hasTime = normalized.includes('T') || normalized.includes(' ');

  if (!hasTime) {
    return normalized;
  }

  // 后端有些字段返回不带时区的时间字符串（例如 2026-04-07T08:34:06），
  // 这里统一按 UTC 解释，再转换为 Asia/Shanghai 展示，避免少 8 小时。
  const date = new Date(hasExplicitTimezone ? normalized : `${normalized}Z`);

  if (Number.isNaN(date.getTime())) {
    return normalized.replace('T', ' ');
  }

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-');
}

export function buildMonthlyTrend(baseTrend = [], tasks = []) {
  const baseTrendMap = baseTrend.reduce((accumulator, item) => {
    if (!item?.month) {
      return accumulator;
    }

    accumulator.set(item.month, {
      month: item.month,
      total: Number(item.total || 0),
      effective: Number(item.effective || 0),
      completed: Number(item.completed || 0),
      taskCount: 0,
      completedTaskCount: 0,
    });
    return accumulator;
  }, new Map());

  const monthlyBuckets = tasks.reduce((accumulator, task) => {
    if (!task.deadline) {
      return accumulator;
    }

    const [, month] = task.deadline.split('-');
    const monthLabel = `${Number(month)}月`;
    const bucket = accumulator.get(monthLabel) ?? {
      month: monthLabel,
      total: baseTrendMap.get(monthLabel)?.total ?? 0,
      effective: 0,
      completed: 0,
      taskCount: 0,
      completedTaskCount: 0,
    };

    bucket.effective += Number(task.hours || 0);
    bucket.taskCount += 1;

    if (task.status === '已完成') {
      bucket.completed += Number(task.hours || 0);
      bucket.completedTaskCount += 1;
    }

    accumulator.set(monthLabel, bucket);
    return accumulator;
  }, new Map(baseTrendMap));

  return Array.from(monthlyBuckets.values())
    .sort((left, right) => Number(left.month.replace('月', '')) - Number(right.month.replace('月', '')))
    .map(({ taskCount, completedTaskCount, ...item }) => ({
      ...item,
      completionRate: item.effective > 0 ? `${Math.round((item.completed / item.effective) * 100)}%` : '0%',
    }));
}
