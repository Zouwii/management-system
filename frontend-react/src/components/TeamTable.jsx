import { useMemo, useState } from 'react';
import {
  LOW_COMPLETION_RATE_THRESHOLD,
  LOW_HOURS_THRESHOLD,
  parseFinalPerformance,
  parseRate,
} from '../utils/managerDashboard';
import { formatDays } from '../utils/workHours';

export default function TeamTable({ rows, showTeam = false }) {
  const [keyword, setKeyword] = useState('');
  const [riskFilter, setRiskFilter] = useState('全部');
  const [performanceFilter, setPerformanceFilter] = useState('全部');
  const [sortBy, setSortBy] = useState('hours-desc');
  const [showAllRows, setShowAllRows] = useState(false);

  const filteredRows = useMemo(() => {
    const normalizedKeyword = keyword.trim();
    const nextRows = rows
      .filter((row) => {
        if (!normalizedKeyword) {
          return true;
        }

        return [row.name, row.role, row.focus, row.team]
          .filter(Boolean)
          .some((value) => String(value).includes(normalizedKeyword));
      })
      .filter((row) => riskFilter === '全部' || row.risk === riskFilter)
      .filter((row) => {
        if (performanceFilter === '全部') {
          return true;
        }

        const finalPerformance = parseFinalPerformance(row);

        if (performanceFilter === '>=1.2') {
          return finalPerformance >= 1.2;
        }

        if (performanceFilter === '1.0-1.2') {
          return finalPerformance >= 1.0 && finalPerformance < 1.2;
        }

        return finalPerformance < 1.0;
      });

    nextRows.sort((left, right) => {
      switch (sortBy) {
        case 'hours-asc':
          return left.hours - right.hours;
        case 'rate-desc':
          return parseRate(right.effectiveRate) - parseRate(left.effectiveRate);
        case 'rate-asc':
          return parseRate(left.effectiveRate) - parseRate(right.effectiveRate);
        case 'hours-desc':
        default:
          return right.hours - left.hours;
      }
    });

    return showAllRows ? nextRows : nextRows.slice(0, 6);
  }, [keyword, performanceFilter, riskFilter, rows, showAllRows, sortBy]);

  return (
    <>
      <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="grid flex-1 gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,1.2fr)_140px_140px_140px]">
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索姓名 / 岗位"
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            />
            <select
              value={riskFilter}
              onChange={(event) => setRiskFilter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            >
              <option value="全部">全部风险</option>
              <option value="低">低风险</option>
              <option value="中">中风险</option>
            </select>
            <select
              value={performanceFilter}
              onChange={(event) => setPerformanceFilter(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            >
              <option value="全部">全部绩效</option>
              <option value=">=1.2">1.2及以上</option>
              <option value="1.0-1.2">1.0 - 1.2</option>
              <option value="<1.0">1.0以下</option>
            </select>
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value)}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
            >
              <option value="hours-desc">工时降序</option>
              <option value="hours-asc">工时升序</option>
              <option value="rate-desc">有效率降序</option>
              <option value="rate-asc">有效率升序</option>
            </select>
          </div>
          <div className="flex items-center justify-between gap-3 xl:justify-end">
            <div className="text-sm text-slate-500">
              当前显示
              {' '}
              <span className="font-semibold text-slate-900">{filteredRows.length}</span>
              {' / '}
              {rows.length}
            </div>
            <button
              type="button"
              onClick={() => setShowAllRows((prev) => !prev)}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              {showAllRows ? '收起' : '展开全部'}
            </button>
          </div>
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-5 py-4 text-left font-medium">姓名</th>
            {showTeam && <th className="px-5 py-4 text-left font-medium">所属组</th>}
            <th className="px-5 py-4 text-left font-medium">岗位</th>
            <th className="px-5 py-4 text-left font-medium">工时</th>
            <th className="px-5 py-4 text-left font-medium">最终绩效</th>
            <th className="px-5 py-4 text-left font-medium">风险</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row, index) => (
            <tr key={`${row.name}-${index}`} className={index !== filteredRows.length - 1 ? 'border-b border-slate-100' : ''}>
              <td className="px-5 py-4 font-medium text-slate-900">{row.name}</td>
              {showTeam && <td className="px-5 py-4 text-slate-600">{row.team}</td>}
              <td className="px-5 py-4 text-slate-600">{row.role}</td>
              <td className="px-5 py-4">
                <div className="flex items-center gap-2 text-slate-600">
                  <span>{formatDays(row.hours)}天</span>
                  {Number(row.hours || 0) < LOW_HOURS_THRESHOLD ? (
                    <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">分配不足</span>
                  ) : null}
                </div>
              </td>
              <td className="px-5 py-4">
                <div className={`flex items-center gap-2 font-medium ${parseFinalPerformance(row) >= 1.0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                  <span>{parseFinalPerformance(row).toFixed(2)}</span>
                  {(parseRate(row.effectiveRate) < LOW_COMPLETION_RATE_THRESHOLD || parseFinalPerformance(row) < 1.0) ? (
                    <span className="rounded-full bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700">完成不足</span>
                  ) : null}
                </div>
              </td>
              <td className="px-5 py-4">
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${row.risk === '低' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                  {row.risk}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
