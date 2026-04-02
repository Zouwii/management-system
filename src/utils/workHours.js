const HOURS_PER_DAY = 8;

function toDate(dateString) {
  const normalized = dateString.includes('T') ? dateString : `${dateString}T00:00:00`;
  return new Date(normalized);
}

function isWeekend(date) {
  const day = date.getDay();
  return day === 0 || day === 6;
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
  let days = 0;
  let holidayCount = 0;

  const start = toDate(startDate);
  const end = toDate(endDate);

  for (let cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    const currentDate = cursor.toISOString().slice(0, 10);

    if (holidaySet.has(currentDate)) {
      holidayCount += 1;
      continue;
    }

    if (!isWeekend(cursor)) {
      days += 1;
    }
  }

  const adjustedDays = Math.max(days - Number(compensatoryDays || 0), 0);

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

  if (!hasExplicitTimezone) {
    return normalized.replace('T', ' ');
  }

  const date = new Date(normalized);

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
      completionRate: taskCount > 0 ? `${Math.round((completedTaskCount / taskCount) * 100)}%` : '0%',
    }));
}
