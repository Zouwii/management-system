import { useEffect, useState } from 'react';
import ManagerLayout from '../layouts/ManagerLayout';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import { fetchApplicationTeamOptions, fetchApplicationTeamReport } from '../api/dashboard';

const TYPE_COLUMNS = ['本体导航/导航', '本体导航/定位', '本体导航/建图', '本体导航/非本体导航'];

function StatTable({ columns, rows, empty = '暂无数据' }) {
  if (!rows?.length) return <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">{empty}</div>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>{columns.map((column) => <th key={column} className="px-3 py-2 font-medium">{column}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row, index) => (
            <tr key={`${row.label}-${index}`}>
              <td className="px-3 py-2 font-medium text-slate-700">{row.label}</td>
              <td className="px-3 py-2 text-slate-600">{row.count}</td>
              <td className="px-3 py-2 text-slate-600">{Number(row.ratio || 0).toFixed(2)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MatrixTable({ matrix, empty = '暂无数据' }) {
  const columns = matrix?.columns || [];
  const rows = matrix?.rows || [];
  if (!rows.length || !columns.length) return <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">{empty}</div>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-3 py-2 font-medium">问题类型\维度</th>
            {columns.map((column) => <th key={column} className="px-3 py-2 text-center font-medium">{column}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {rows.map((row) => (
            <tr key={row.label}>
              <td className="px-3 py-2 font-medium text-slate-700">{row.label}</td>
              {columns.map((column) => <td key={column} className="px-3 py-2 text-center text-slate-600">{row.values?.[column] ?? 0}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ApplicationTeamPage({ user, scopeCode = 'APPLICATION_TEAM_VIEW', pageTitle = '应用组问题分析', pageDescription = '独立于有效工时的应用组问题处理统计' }) {
  const currentYear = new Date().getFullYear();
  const [filterOptions, setFilterOptions] = useState({ years: [currentYear], quarters: [1, 2, 3, 4], members: [] });
  const [year, setYear] = useState(currentYear);
  const [quarter, setQuarter] = useState(2);
  const [executorId, setExecutorId] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    fetchApplicationTeamOptions(user, { scopeCode })
      .then((response) => {
        if (!active) return;
        const data = response?.data || {};
        const years = Array.isArray(data.years) && data.years.length ? data.years : [currentYear];
        const quarters = Array.isArray(data.quarters) && data.quarters.length ? data.quarters : [1, 2, 3, 4];
        setFilterOptions({ years, quarters, members: data.members || [] });
        setYear((previous) => (years.includes(previous) ? previous : years[0]));
        setQuarter((previous) => (quarters.includes(previous) ? previous : quarters[0]));
      })
      .catch((reason) => {
        if (active) setError(reason?.message || '应用组问题报表查询失败');
      })
      .finally(() => { if (active) setOptionsLoading(false); });
    return () => { active = false; };
  }, [currentYear, user, scopeCode]);

  const queryReport = () => {
    setLoading(true);
    setError('');
    fetchApplicationTeamReport(user, { year, quarter, executorId, scopeCode })
      .then((response) => setReport(response?.data || {}))
      .catch((reason) => setError(reason?.message || '应用组问题报表查询失败'))
      .finally(() => setLoading(false));
  };

  const typeRows = report?.typeStats?.rows || [];
  return (
    <ManagerLayout>
      <Card className="p-5 lg:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionTitle title={pageTitle} description={pageDescription} />
          <div className="flex flex-wrap items-center gap-2">
            <select value={year} onChange={(event) => setYear(Number(event.target.value))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              {filterOptions.years.map((item) => <option key={item} value={item}>{item}年</option>)}
            </select>
            <select value={quarter} onChange={(event) => setQuarter(Number(event.target.value))} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              {filterOptions.quarters.map((item) => <option key={item} value={item}>Q{item}</option>)}
            </select>
            <select value={executorId} onChange={(event) => setExecutorId(event.target.value)} className="min-w-32 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              <option value="">全部用户</option>
              {filterOptions.members.map((item) => <option key={item.userId} value={item.userId}>{item.name}</option>)}
            </select>
            <button type="button" onClick={queryReport} disabled={loading || optionsLoading} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">查询</button>
          </div>
        </div>
        {loading || optionsLoading ? <div className="mt-6 text-sm text-slate-500">正在加载应用组查询条件…</div> : null}
        {error ? <div className="mt-6 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</div> : null}
        {!loading && !optionsLoading && !error && !report ? <div className="mt-6 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">请选择季度和用户后点击“查询”。</div> : null}
        {!loading && !optionsLoading && !error && report ? (
          <div className="mt-6 space-y-6">
            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">问题类型统计（{report?.total || 0} 单）</h2>
              <StatTable columns={['问题类型', '单数', '占比']} rows={typeRows} />
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">问题原因统计</h2>
              <div className="grid gap-4 xl:grid-cols-3">
                {(report?.causeStats || []).map((section) => (
                  <div key={section.type} className="space-y-3">
                    <h3 className="text-sm font-semibold text-slate-700">{section.type}原因分类统计</h3>
                    <StatTable columns={['原因类型', '单数', '占比']} rows={section.rows} />
                    {Object.entries(section.secondary || {}).map(([label, rows]) => (
                      <div key={label}>
                        <h4 className="mb-2 text-xs font-medium text-slate-500">{label}二级分类</h4>
                        <StatTable columns={['原因路径', '单数', '占比']} rows={rows} />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">问题提示信息统计</h2>
              <div className="grid gap-4 xl:grid-cols-2">
                {(report?.promptStats || []).map((section) => (
                  <div key={section.type}><h3 className="mb-2 text-sm font-semibold text-slate-700">{section.type}</h3><StatTable columns={['提示信息类型', '单数', '占比']} rows={section.rows} /></div>
                ))}
              </div>
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">优先级</h2>
              <MatrixTable matrix={report?.priorityMatrix} />
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">排查文档价值</h2>
              <MatrixTable matrix={report?.documentValueMatrix} empty="排查文档价值字段尚未接入" />
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-slate-900">项目（本体项目分类）</h2>
              <MatrixTable matrix={report?.projectMatrix} />
            </section>

            <section className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              已关联现场单：<span className="font-semibold text-slate-900">{report?.onsiteLinks?.count || 0}</span> 单
            </section>
          </div>
        ) : null}
      </Card>
    </ManagerLayout>
  );
}
