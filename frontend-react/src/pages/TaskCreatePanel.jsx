const fieldClass = 'w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[13px] leading-5 text-slate-800 outline-none transition focus:border-sky-300';
const labelClass = 'mb-1 text-[12px] font-medium leading-4 text-slate-500';

export default function TaskCreatePanel({
  draft,
  setDraft,
  taskList,
  parentSelectorOpen,
  setParentSelectorOpen,
  outputWarnings,
  createResult,
  WORK_TYPES,
  PARTICIPATION_LEVELS,
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="space-y-2.5 p-3">
        {outputWarnings.length > 0 ? (
          <div className="space-y-1">
            {outputWarnings.map((warning, index) => (
              <div key={index} className="rounded-md bg-amber-50 px-2 py-1 text-[12px] leading-5 text-amber-700">{warning}</div>
            ))}
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className={labelClass}>任务标题</div>
            <input
              type="text"
              className={`${fieldClass} font-semibold`}
              value={draft.title}
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              placeholder="等待 Claude 生成..."
            />
          </div>

          <div>
            <div className={labelClass}>父任务（可选）</div>
            <div className="relative">
              <button
                type="button"
                className={`${fieldClass} flex items-center justify-between text-left`}
                onClick={() => setParentSelectorOpen((prev) => !prev)}
              >
                <span className={`truncate ${draft.parentTaskId ? '' : 'text-slate-400'}`}>
                  {draft.parentTaskId
                    ? (taskList.find((task) => task.taskId === draft.parentTaskId)?.title || draft.parentTaskId)
                    : '不选择父任务'}
                </span>
                <svg className={`h-4 w-4 shrink-0 text-slate-400 transition ${parentSelectorOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
              </button>
              {parentSelectorOpen ? (
                <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left text-[13px] leading-5 text-slate-400 transition hover:bg-slate-50"
                    onClick={() => { setDraft((current) => ({ ...current, parentTaskId: '' })); setParentSelectorOpen(false); }}
                  >
                    不选择父任务
                  </button>
                  {taskList.map((item) => (
                    <button
                      key={item.taskId}
                      type="button"
                      className={`w-full px-3 py-2 text-left text-[13px] leading-5 transition hover:bg-slate-50 ${draft.parentTaskId === item.taskId ? 'bg-sky-50 font-medium text-sky-700' : 'text-slate-700'}`}
                      onClick={() => { setDraft((current) => ({ ...current, parentTaskId: item.taskId })); setParentSelectorOpen(false); }}
                    >
                      <span className="line-clamp-1">{item.title}</span>
                      <span className="text-[11px] text-slate-400">{item.taskId}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className={labelClass}>开始日期</div>
            <input
              type="date"
              className={fieldClass}
              value={draft.startDate ? draft.startDate.slice(0, 10) : ''}
              onChange={(event) => setDraft((current) => ({ ...current, startDate: event.target.value }))}
            />
          </div>
          <div>
            <div className={labelClass}>结束日期</div>
            <input
              type="date"
              className={fieldClass}
              value={draft.dueDate ? draft.dueDate.slice(0, 10) : ''}
              onChange={(event) => setDraft((current) => ({ ...current, dueDate: event.target.value }))}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className={labelClass}>需求描述</div>
            <textarea
              className={`${fieldClass} min-h-[118px] resize-y`}
              value={draft.requirementDesc}
              onChange={(event) => setDraft((current) => ({ ...current, requirementDesc: event.target.value }))}
              placeholder="等待 Claude 填写..."
            />
          </div>

          <div>
            <div className={labelClass}>任务产出</div>
            <div className="space-y-1.5">
              {draft.outputs.length > 0 ? (
                draft.outputs.map((item, index) => (
                  <div key={index} className="flex items-center gap-1.5">
                    <input
                      type="text"
                      className={fieldClass}
                      value={item}
                      onChange={(event) => {
                        const next = [...draft.outputs];
                        next[index] = event.target.value;
                        setDraft((current) => ({ ...current, outputs: next }));
                      }}
                    />
                    <button
                      type="button"
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-slate-200 text-slate-400 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                      onClick={() => {
                        const next = draft.outputs.filter((_, i) => i !== index);
                        setDraft((current) => ({ ...current, outputs: next }));
                      }}
                      aria-label="删除产出"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                ))
              ) : (
                <div className="rounded-md border border-dashed border-slate-200 px-2 py-2 text-[12px] text-slate-400">等待 Claude 填写...</div>
              )}
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700"
                onClick={() => setDraft((current) => ({ ...current, outputs: [...current.outputs, ''] }))}
                title="添加产出"
                aria-label="添加产出"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.2} stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14m7-7H5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className={labelClass}>工时类型</div>
            <select
              className={fieldClass}
              value={draft.workType}
              onChange={(event) => setDraft((current) => ({ ...current, workType: event.target.value }))}
            >
              {WORK_TYPES.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div>
            <div className={labelClass}>参与度（人天）</div>
            <select
              className={fieldClass}
              value={draft.participationLevel}
              onChange={(event) => setDraft((current) => ({ ...current, participationLevel: Number(event.target.value) }))}
            >
              {PARTICIPATION_LEVELS.map((item) => (
                <option key={item} value={item}>{item} 人天</option>
              ))}
            </select>
          </div>
        </div>

        {createResult ? (
          <div className="rounded-md border border-emerald-100 bg-emerald-50 px-2.5 py-2 text-[12px] leading-5 text-emerald-800">
            <div className="font-semibold">{createResult.message}</div>
            {createResult.taskUrl ? (
              <a href={createResult.taskUrl} target="_blank" rel="noopener noreferrer" className="break-all text-emerald-700 underline hover:text-emerald-900">
                {createResult.taskUrl}
              </a>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
