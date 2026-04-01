import { useEffect, useState } from 'react';
import { fetchAIInsightList } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import StatCard from '../components/StatCard';
import EmployeeLayout from '../layouts/EmployeeLayout';
import { aiInsightList as fallbackData } from '../mock/platformData';

export default function AIAnalysisPage() {
  const [insights, setInsights] = useState(fallbackData);
  const insightTypeClassMap = {
    效率优化: 'border-cyan-100 bg-cyan-50 text-cyan-700',
    绩效关联: 'border-violet-100 bg-violet-50 text-violet-700',
    风险提醒: 'border-amber-100 bg-amber-50 text-amber-700',
    能力发展: 'border-emerald-100 bg-emerald-50 text-emerald-700',
  };

  useEffect(() => {
    let active = true;

    fetchAIInsightList().then((response) => {
      if (active) {
        setInsights(response.data);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <EmployeeLayout>
      <SectionTitle
        title="AI 分析中心"
        desc="员工端AI页面应以可执行建议为主，不暴露组织级比较和他人数据。"
        right={<div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">AI 每周更新</div>}
      />
      <div className="grid grid-cols-4 gap-5">
        <StatCard title="本周建议数" value="4" sub="效率优化 / 绩效关联 / 风险提醒 / 成长建议" />
        <StatCard title="风险级别" value="中低" sub="排查任务连续增加，需关注时间分配" />
        <StatCard title="推荐动作" value="3项" sub="任务聚焦、沉淀输出、减少碎片化支持" />
        <StatCard title="成长方向" value="控制优化" sub="适合持续承担复杂技术任务" />
      </div>
      <div className="grid grid-cols-2 gap-5">
        {insights.map((item) => (
          <Card key={item.title} className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="text-lg font-semibold">{item.title}</div>
              <div className={`rounded-full border px-3 py-1 text-xs font-medium ${insightTypeClassMap[item.type] ?? 'border-slate-200 bg-slate-100 text-slate-700'}`}>{item.type}</div>
            </div>
            <div className="mt-3 text-sm leading-7 text-slate-600">{item.content}</div>
          </Card>
        ))}
      </div>
    </EmployeeLayout>
  );
}
