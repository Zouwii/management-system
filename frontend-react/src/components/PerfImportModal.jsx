import { useEffect, useState } from 'react';
import { fetchTeamImportUsers, batchImportScores } from '../api/dashboard';
import Card from './Card';

const CURRENT_YEAR = 2025;
const QUARTERS = [1, 2, 3, 4];
const TEAMS = [
  { key: 'nav', label: '导航组' },
  { key: 'servo', label: '对接组' },
];

export default function PerfImportModal({ open, onClose }) {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [quarter, setQuarter] = useState(2);
  const [team, setTeam] = useState('nav');
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setMessage('');
    fetchTeamImportUsers({ year, quarter, team })
      .then((res) => {
        if (res?.data?.members) {
          setMembers(res.data.members.map((m) => ({
            ...m,
            _wh: m.workHourScore ?? '',
            _sp: m.supervisorScore ?? '',
          })));
        }
      })
      .catch(() => setMessage('加载失败'))
      .finally(() => setLoading(false));
  }, [open, year, quarter, team]);

  const handleSave = async () => {
    const toSave = members
      .filter((m) => m._wh !== '' || m._sp !== '')
      .map((m) => ({
        userId: m.userId,
        workHourScore: m._wh === '' ? null : parseFloat(m._wh),
        supervisorScore: m._sp === '' ? null : parseFloat(m._sp),
      }));

    if (toSave.length === 0) {
      setMessage('没有需要保存的数据');
      return;
    }

    setSaving(true);
    setMessage('');
    try {
      const res = await batchImportScores({ year, quarter, team, members: toSave });
      if (res?.data?.ok !== undefined) {
        setMessage(`导入完成: ${res.data.ok} 成功, ${res.data.fail} 失败`);
      }
    } catch {
      setMessage('保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <Card className="w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">导入绩效数据</h2>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>

        {/* filters */}
        <div className="flex gap-3 px-6 py-3 border-b border-slate-100 bg-slate-50">
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none"
          >
            {[2024, 2025, 2026].map((y) => (
              <option key={y} value={y}>{y}年</option>
            ))}
          </select>
          <select
            value={quarter}
            onChange={(e) => setQuarter(Number(e.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none"
          >
            {QUARTERS.map((q) => (
              <option key={q} value={q}>Q{q}</option>
            ))}
          </select>
          <select
            value={team}
            onChange={(e) => setTeam(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none"
          >
            {TEAMS.map((t) => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
          <button
            onClick={() => {
              setMembers([]);
              setLoading(true);
              fetchTeamImportUsers({ year, quarter, team })
                .then((res) => {
                  if (res?.data?.members) {
                    setMembers(res.data.members.map((m) => ({
                      ...m,
                      _wh: m.workHourScore ?? '',
                      _sp: m.supervisorScore ?? '',
                    })));
                  }
                })
                .finally(() => setLoading(false));
            }}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
          >
            刷新
          </button>
        </div>

        {/* table */}
        <div className="overflow-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-slate-400">加载中...</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-left font-medium w-10"></th>
                  <th className="px-5 py-3 text-left font-medium">姓名</th>
                  <th className="px-5 py-3 text-left font-medium">工时绩效</th>
                  <th className="px-5 py-3 text-left font-medium">主管评分</th>
                  <th className="px-5 py-3 text-left font-medium w-24">状态</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m, i) => (
                  <tr key={m.userId} className={i !== members.length - 1 ? 'border-b border-slate-100' : ''}>
                    <td className="px-5 py-2.5">
                      {m.isTeamLead ? (
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 text-xs text-amber-700" title="组长">★</span>
                      ) : null}
                    </td>
                    <td className="px-5 py-2.5 font-medium text-slate-900">{m.userName}</td>
                    <td className="px-5 py-2.5">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="3"
                        value={m._wh}
                        onChange={(e) => {
                          const copy = [...members];
                          copy[i] = { ...copy[i], _wh: e.target.value };
                          setMembers(copy);
                        }}
                        className="w-20 rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm outline-none transition focus:border-sky-400 focus:ring-1 focus:ring-sky-200"
                        placeholder="1.0"
                      />
                    </td>
                    <td className="px-5 py-2.5">
                      <select
                        value={m._sp}
                        onChange={(e) => {
                          const copy = [...members];
                          copy[i] = { ...copy[i], _sp: e.target.value };
                          setMembers(copy);
                        }}
                        className="w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-sm outline-none transition focus:border-sky-400 focus:ring-1 focus:ring-sky-200"
                      >
                        <option value="">-</option>
                        {[0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0].map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-5 py-2.5">
                      {m.calcStatus === 'calculated' ? (
                        <span className="text-xs text-emerald-600">已计算</span>
                      ) : m.calcStatus === 'filled' ? (
                        <span className="text-xs text-sky-600">待计算</span>
                      ) : (
                        <span className="text-xs text-slate-400">未导入</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* footer */}
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4">
          <span className={`text-sm ${message.includes('失败') ? 'text-rose-600' : 'text-emerald-600'}`}>
            {message}
          </span>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="rounded-xl border border-slate-200 bg-white px-5 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            >
              关闭
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
