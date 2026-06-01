import { useState } from 'react';

export default function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = true,
  children,
  extra,
  onToggle,
}) {
  const [open, setOpen] = useState(defaultOpen);

  function handleToggle() {
    const next = !open;
    setOpen(next);
    if (onToggle) onToggle(next);
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white">
      {/* header */}
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50"
      >
        <div className="flex items-center gap-3">
          <svg
            className={`h-4 w-4 text-slate-400 transition ${open ? 'rotate-90' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
          <div>
            <span className="text-lg font-semibold text-slate-900">{title}</span>
            {subtitle ? (
              <span className="ml-2 text-sm text-slate-400">{subtitle}</span>
            ) : null}
          </div>
        </div>
        {extra ? <div onClick={(e) => e.stopPropagation()}>{extra}</div> : null}
      </button>

      {/* body */}
      {open ? <div className="border-t border-slate-100 px-5 pb-5">{children}</div> : null}
    </div>
  );
}
