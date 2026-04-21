const FINAL_PERFORMANCE_MAP = {
  A: 1.2,
  'A-': 1.2,
  'B+': 1.0,
  B: 0.8,
};

export const LOW_HOURS_THRESHOLD = 150;
export const LOW_COMPLETION_RATE_THRESHOLD = 80;

export function getCurrentLocalDateTime() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutePart = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day}T${hours}:${minutePart}:${seconds}`;
}

export function parseRate(value) {
  return Number(String(value ?? '0').replace('%', '')) || 0;
}

export function parseTrendHours(value) {
  return Number(String(value ?? '0').replace(/[^\d+-]/g, '')) || 0;
}

export function parseFinalPerformance(row) {
  return Number(row.finalPerformance ?? FINAL_PERFORMANCE_MAP[row.perf] ?? 0);
}

export function buildTeamSummary(rows) {
  const totalHours = rows.reduce((sum, row) => sum + Number(row.hours || 0), 0);
  const avgEffectiveRate = rows.length
    ? `${Math.round(rows.reduce((sum, row) => sum + parseRate(row.effectiveRate), 0) / rows.length)}%`
    : '0%';
  const avgFinalPerformance = rows.length
    ? (rows.reduce((sum, row) => sum + parseFinalPerformance(row), 0) / rows.length).toFixed(2)
    : '0.00';
  const mediumRiskCount = rows.filter((row) => row.risk !== '低').length;
  const positiveTrendCount = rows.filter((row) => parseTrendHours(row.trend) > 0).length;
  const topMember = [...rows].sort((left, right) => Number(right.hours || 0) - Number(left.hours || 0))[0];
  const lowHoursMembers = rows.filter((row) => Number(row.hours || 0) < LOW_HOURS_THRESHOLD);
  const lowCompletionMembers = rows.filter((row) => parseRate(row.effectiveRate) < LOW_COMPLETION_RATE_THRESHOLD || parseFinalPerformance(row) < 1.0);

  return {
    totalMembers: rows.length,
    totalHours,
    avgEffectiveRate,
    avgFinalPerformance,
    mediumRiskCount,
    positiveTrendCount,
    topMember,
    lowHoursMembers,
    lowCompletionMembers,
  };
}

export function buildDepartmentDistribution(rows) {
  const totalHours = rows.reduce((sum, row) => sum + Number(row.hours || 0), 0);
  const teamMap = rows.reduce((accumulator, row) => {
    const next = accumulator;
    const current = next.get(row.team) ?? 0;
    next.set(row.team, current + Number(row.hours || 0));
    return next;
  }, new Map());

  return Array.from(teamMap.entries())
    .map(([team, hours]) => ({
      team,
      hours,
      ratio: totalHours > 0 ? Math.round((hours / totalHours) * 100) : 0,
    }))
    .sort((left, right) => right.hours - left.hours);
}

export function buildRiskRows(rows) {
  return [...rows]
    .filter((row) => row.risk !== '低')
    .sort((left, right) => Number(right.hours || 0) - Number(left.hours || 0));
}

export function buildTeamTrend(rows) {
  return [...rows]
    .map((row) => ({
      ...row,
      trendHours: parseTrendHours(row.trend),
    }))
    .sort((left, right) => right.trendHours - left.trendHours);
}
