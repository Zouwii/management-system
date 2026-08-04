export default function SectionTitle({ title, desc, right }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <div className="text-xl font-semibold text-slate-900 sm:text-2xl">{title}</div>
        {desc ? <div className="mt-2 text-sm text-slate-500">{desc}</div> : null}
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  );
}
