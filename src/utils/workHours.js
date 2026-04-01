const HOURS_PER_DAY = 8;

function toDate(dateString) {
  const normalized = dateString.includes('T') ? dateString : `${dateString}T00:00:00`;
  return new Date(normalized);
}

function isWeekend(date) {
  const day = date.getDay();
  return day === 0 || day === 6;
}

export function calculateExpectedEffectiveDays(startDate, endDate, holidays = []) {
  if (!startDate || !endDate || startDate > endDate) {
    return {
      days: 0,
      hours: 0,
      holidayCount: 0,
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

  return {
    days,
    hours: days * HOURS_PER_DAY,
    holidayCount,
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

  return value.length === 16 ? `${value}:00` : value;
}
