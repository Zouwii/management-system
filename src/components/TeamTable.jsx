export default function TeamTable({ rows, showTeam = false }) {
  const performanceTagClassMap = {
    A: 'bg-emerald-50 text-emerald-700',
    'A-': 'bg-teal-50 text-teal-700',
    'B+': 'bg-amber-50 text-amber-700',
    B: 'bg-orange-50 text-orange-700',
  };

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-5 py-4 text-left font-medium">姓名</th>
            {showTeam && <th className="px-5 py-4 text-left font-medium">所属组</th>}
            <th className="px-5 py-4 text-left font-medium">岗位</th>
            <th className="px-5 py-4 text-left font-medium">级别</th>
            <th className="px-5 py-4 text-left font-medium">有效工时</th>
            <th className="px-5 py-4 text-left font-medium">有效率</th>
            <th className="px-5 py-4 text-left font-medium">绩效</th>
            <th className="px-5 py-4 text-left font-medium">风险</th>
            <th className="px-5 py-4 text-left font-medium">核心事项</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.name}-${index}`} className={index !== rows.length - 1 ? 'border-b border-slate-100' : ''}>
              <td className="px-5 py-4 font-medium text-slate-900">{row.name}</td>
              {showTeam && <td className="px-5 py-4 text-slate-600">{row.team}</td>}
              <td className="px-5 py-4 text-slate-600">{row.role}</td>
              <td className="px-5 py-4 text-slate-600">{row.level}</td>
              <td className="px-5 py-4 text-slate-600">{row.hours}h</td>
              <td className="px-5 py-4 text-slate-600">{row.effectiveRate}</td>
              <td className="px-5 py-4">
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${performanceTagClassMap[row.perf] ?? 'bg-slate-100 text-slate-700'}`}>{row.perf}</span>
              </td>
              <td className="px-5 py-4">
                <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${row.risk === '低' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                  {row.risk}
                </span>
              </td>
              <td className="px-5 py-4 text-slate-600">{row.focus}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
