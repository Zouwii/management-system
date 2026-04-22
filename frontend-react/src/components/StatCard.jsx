import Card from './Card';

export default function StatCard({ title, value, sub, valueAlign = 'left' }) {
  const isRightAligned = valueAlign === 'right';
  return (
    <Card className="p-5">
      <div className="text-sm text-slate-500">{title}</div>
      <div className={`mt-2 flex min-h-[72px] items-center ${isRightAligned ? 'justify-end' : ''}`}>
        <div className={`text-3xl font-semibold text-slate-900 ${isRightAligned ? 'text-right' : ''}`}>{value}</div>
      </div>
      <div className="mt-2 text-sm leading-6 text-slate-500">{sub}</div>
    </Card>
  );
}
