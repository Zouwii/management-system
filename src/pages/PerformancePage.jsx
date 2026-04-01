import { useEffect, useState } from 'react';
import { fetchPerformanceHistory } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { performanceHistory as fallbackData } from '../mock/platformData';

export default function PerformancePage() {
  const [history, setHistory] = useState(fallbackData);
  const scoreTagClassMap = {
    A: 'bg-emerald-50 text-emerald-700',
    'A-': 'bg-teal-50 text-teal-700',
    'B+': 'bg-amber-50 text-amber-700',
    B: 'bg-orange-50 text-orange-700',
  };

  useEffect(() => {
    let active = true;

    fetchPerformanceHistory().then((response) => {
      if (active) {
        setHistory(response.data);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <EmployeeLayout>
      <SectionTitle
        title="个人绩效管理"
        desc="员工端只查看本人绩效结果、变化趋势和改进建议，不展示他人排名明细。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">季度同步更新</div>}
      />
      <div className="grid grid-cols-4 gap-5">
        <StatCard title="当前绩效" value="A" sub="2026 Q1 结果" />
        <StatCard title="本季度提升" value="+1档" sub="较 2025 Q3 明显改善" />
        <StatCard title="研发型任务占比" value="高" sub="对绩效形成正向支撑" />
        <StatCard title="短板项" value="成果沉淀" sub="文档化与经验输出仍可加强" />
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">绩效历史</div>
          <div className="mt-1 text-sm text-slate-500">保留趋势感，但避免展示过度敏感的组织内明细比较。</div>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">季度</th>
                <th className="px-5 py-4 text-left font-medium">绩效</th>
                <th className="px-5 py-4 text-left font-medium">相对表现</th>
                <th className="px-5 py-4 text-left font-medium">说明</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item, index) => (
                <tr key={item.quarter} className={index !== history.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-5 py-4 font-medium">{item.quarter}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${scoreTagClassMap[item.score] ?? 'bg-slate-100 text-slate-700'}`}>{item.score}</span>
                  </td>
                  <td className="px-5 py-4 text-slate-600">{item.rank}</td>
                  <td className="px-5 py-4 text-slate-600">{item.comment}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </EmployeeLayout>
  );
}
