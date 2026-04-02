export default function SectionTitle({ title, desc, right }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <div className="text-2xl font-semibold text-slate-900">{title}</div>
        <div className="mt-2 text-sm text-slate-500">{desc}</div>
      </div>
      {right}
    </div>
  );
}
