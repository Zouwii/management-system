import { useEffect, useState } from 'react';
import { fetchTeamImportUsers, batchImportScores, updateMemberPerformance, fetchTeams, recalcMemberPerformance } from '../api/dashboard';
import Card from './Card';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = Math.floor(new Date().getMonth() / 3) + 1;
const QUARTERS = [1, 2, 3, 4];

function toNum(v) { return v === '' || v == null ? null : parseFloat(v); }

export default function PerfImportModal({ open, onClose }) {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [quarter, setQuarter] = useState(CURRENT_QUARTER);
  const [team, setTeam] = useState('nav');
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [recalcing, setRecalcing] = useState(null); // userId being recalculated
  const [message, setMessage] = useState('');
  const [editCalc, setEditCalc] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [teams, setTeams] = useState([]);

  useEffect(() => {
    if (!open) return;
    fetchTeams().then((res) => {
      const list = res?.data?.teams || [];
      setTeams(list);
      if (list.length && !list.find((t) => t.key === team)) {
        setTeam(list[0].key);
      }
    }).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setMessage('');
    fetchTeamImportUsers({ year, quarter, team })
      .then((res) => {
        if (res?.data?.members) {
          setMembers(res.data.members.map((m) => ({
            ...m,
            _wh:  m.workHourScore       ?? '',
            _sp:  m.supervisorScore     ?? '',
            _pcb: m.prevCarryBalance    ?? 0,
            _os:  m.overallScore        ?? '',
            _cv:  m.compensationValue   ?? '',
            _ov:  m.overflowValue       ?? '',
            _fs:  m.finalScore          ?? '',
            _ncb: m.newCarryBalance     ?? '',
            _cdv: m.carryDecayValue     ?? '',
            _cs:  m.companyScore        ?? '',
          })));
        }
      })
      .catch(() => setMessage('加载失败'))
      .finally(() => setLoading(false));
  }, [open, year, quarter, team]);

  const handleSave = async () => {
    setSaving(true);
    setMessage('');

    try {
      if (editCalc) {
        const editable = members.filter((m) =>
          m._wh !== '' || m._sp !== '' || m.calcStatus
        );
        if (editable.length === 0) {
          setMessage('没有需要保存的数据');
          setSaving(false);
          return;
        }

        let ok = 0, fail = 0;
        for (const m of editable) {
          try {
            await updateMemberPerformance({
              year, quarter,
              userId: m.userId,
              workHourScore: toNum(m._wh),
              supervisorScore: toNum(m._sp),
              prevCarryBalance: toNum(m._pcb),
              prevDecayValue: (toNum(m._pcb) || 0) * 0.25,
              overallScore: toNum(m._os),
              compensationValue: toNum(m._cv),
              overflowValue: toNum(m._ov),
              finalScore: toNum(m._fs),
              newCarryBalance: toNum(m._ncb),
              carryDecayValue: toNum(m._cdv),
              companyScore: toNum(m._cs),
              calcStatus: m.calcStatus,
            });
            ok++;
          } catch {
            fail++;
          }
        }
        setMessage(`保存完成: ${ok} 成功, ${fail} 失败`);
      } else {
        const toSave = members
          .filter((m) => m._wh !== '' || m._sp !== '')
          .map((m) => {
            const item = {
              userId: m.userId,
              workHourScore: toNum(m._wh),
              supervisorScore: toNum(m._sp),
            };
            // 用户手动改了上季结余才传，否则后端自动查询
            if (parseFloat(m._pcb || 0) !== 0) {
              item.prevCarryBalance = parseFloat(m._pcb);
            }
            return item;
          });

        if (toSave.length === 0) {
          setMessage('没有需要保存的数据');
          setSaving(false);
          return;
        }

        const res = await batchImportScores({ year, quarter, team, members: toSave });
        if (res?.data?.ok !== undefined) {
          setMessage(`导入完成: ${res.data.ok} 成功, ${res.data.fail} 失败`);
        }
      }
    } catch {
      setMessage('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleRecalc = async (userId) => {
    const m = members.find((x) => x.userId === userId);
    if (!m) return;
    setRecalcing(userId);
    try {
      // 先保存当前表单值
      if (editCalc) {
        await updateMemberPerformance({
          year, quarter, userId,
          workHourScore: toNum(m._wh),
          supervisorScore: toNum(m._sp),
          prevCarryBalance: toNum(m._pcb),
          prevDecayValue: (toNum(m._pcb) || 0) * 0.25,
          overallScore: toNum(m._os),
          compensationValue: toNum(m._cv),
          overflowValue: toNum(m._ov),
          finalScore: toNum(m._fs),
          newCarryBalance: toNum(m._ncb),
          carryDecayValue: toNum(m._cdv),
          companyScore: toNum(m._cs),
          calcStatus: m.calcStatus,
        });
      } else {
        await batchImportScores({
          year, quarter, team,
          members: [{
            userId,
            workHourScore: toNum(m._wh),
            supervisorScore: toNum(m._sp),
          }],
        });
      }
      // 再触发计算
      await recalcMemberPerformance({ year, quarter, userId });
      // 刷新数据
      const res = await fetchTeamImportUsers({ year, quarter, team });
      if (res?.data?.members) {
        setMembers(res.data.members.map((r) => ({
          ...r,
          _wh:  r.workHourScore       ?? '',
          _sp:  r.supervisorScore     ?? '',
          _pcb: r.prevCarryBalance    ?? 0,
          _os:  r.overallScore        ?? '',
          _cv:  r.compensationValue   ?? '',
          _ov:  r.overflowValue       ?? '',
          _fs:  r.finalScore          ?? '',
          _ncb: r.newCarryBalance     ?? '',
          _cdv: r.carryDecayValue     ?? '',
          _cs:  r.companyScore        ?? '',
        })));
      }
    } catch {
      // ignore
    } finally {
      setRecalcing(null);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <Card className={`w-full ${editCalc ? 'max-w-6xl' : 'max-w-3xl'} max-h-[85vh] flex flex-col`}>
        {/* header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">导入/编辑</h2>
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
        <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-100 bg-slate-50 flex-wrap">
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
            {teams.map((t) => (
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
                      _wh:  m.workHourScore       ?? '',
                      _sp:  m.supervisorScore     ?? '',
                      _pcb: m.prevCarryBalance    ?? 0,
                      _pdv: m.prevDecayValue      ?? 0,
                      _os:  m.overallScore        ?? '',
                      _cv:  m.compensationValue   ?? '',
                      _ov:  m.overflowValue       ?? '',
                      _fs:  m.finalScore          ?? '',
                      _ncb: m.newCarryBalance     ?? '',
                      _cdv: m.carryDecayValue     ?? '',
                      _cs:  m.companyScore        ?? '',
                    })));
                  }
                })
                .finally(() => setLoading(false));
            }}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
          >
            刷新
          </button>
          <span className="ml-auto" />
          <button
            onClick={() => setEditCalc((v) => !v)}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
              editCalc
                ? 'border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700'
            }`}
          >
            {editCalc ? '收起计算结果' : '编辑计算结果'}
          </button>
          <button
            onClick={() => editCalc && setShowDetail((v) => !v)}
            disabled={!editCalc}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
              !editCalc
                ? 'border-slate-100 bg-slate-50 text-slate-300 cursor-not-allowed'
                : showDetail
                  ? 'border-violet-300 bg-violet-50 text-violet-700 hover:bg-violet-100'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700'
            }`}
          >
            {showDetail ? '收起明细' : '展开明细'}
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
                  <th className="px-4 py-3 text-left font-medium w-10"></th>
                  <th className="px-3 py-3 text-left font-medium">姓名</th>
                  <th className="px-3 py-3 text-left font-medium bg-blue-100/50 text-blue-700">工时绩效</th>
                  <th className="px-3 py-3 text-left font-medium bg-blue-100/50 text-blue-700">主管评分</th>
                  {editCalc ? (
                    <th className="px-2 py-3 text-left font-medium">上季结余</th>
                  ) : null}
                  {showDetail && editCalc ? (
                    <th className="px-2 py-3 text-left font-medium text-slate-400">上季衰减</th>
                  ) : null}
                  {editCalc ? (
                    <>
                      <th className="px-2 py-3 text-left font-medium bg-emerald-100/50 text-emerald-700">总体绩效</th>
                      {showDetail ? (
                        <>
                          <th className="px-1 py-3 text-left font-medium text-slate-400">补偿值</th>
                          <th className="px-1 py-3 text-left font-medium text-slate-400">溢出值</th>
                        </>
                      ) : null}
                      <th className="px-2 py-3 text-left font-medium bg-orange-100/50 text-orange-700">最终绩效</th>
                      <th className="px-2 py-3 text-left font-medium">本季度结余</th>
                      {showDetail ? (
                        <>
                          <th className="px-1 py-3 text-left font-medium text-slate-400">衰减值</th>
                          <th className="px-1 py-3 text-left font-medium text-slate-400">公司绩效</th>
                        </>
                      ) : null}
                    </>
                  ) : null}
                  <th className="px-4 py-3 text-left font-medium w-20">状态</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m, i) => (
                  <tr key={m.userId} className={i !== members.length - 1 ? 'border-b border-slate-100' : ''}>
                    <td className="px-4 py-2">
                      {m.isTeamLead ? (
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 text-xs text-amber-700" title="组长">★</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 font-medium text-slate-900">{m.userName}</td>
                    <td className="px-3 py-2">
                      <input type="number" step="0.01" min="0" max="3" value={m._wh}
                        onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _wh: e.target.value }; setMembers(cp); }}
                        className="w-18 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200" placeholder="1.0" />
                    </td>
                    <td className="px-3 py-2">
                      <select value={m._sp}
                        onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _sp: e.target.value }; setMembers(cp); }}
                        className="w-20 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200">
                        <option value="">-</option>
                        {[0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0].map((v) => (<option key={v} value={v}>{v}</option>))}
                      </select>
                    </td>
                    {editCalc ? (
                      <td className="px-2 py-2">
                        <input type="number" step="0.001" min="0" max="5" value={m._pcb}
                          onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _pcb: e.target.value }; setMembers(cp); }}
                          className="w-18 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200" placeholder="0" />
                      </td>
                    ) : null}
                    {showDetail && editCalc ? (
                      <td className="px-2 py-2 text-xs text-slate-400">
                        {(parseFloat(m._pcb || 0) * 0.25).toFixed(3)}
                      </td>
                    ) : null}
                    {editCalc ? (
                      <>
                        <td className="px-2 py-2">
                          <input type="number" step="0.001" min="0" max="5" value={m._os}
                            onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _os: e.target.value }; setMembers(cp); }}
                            className="w-18 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200" />
                        </td>
                        {showDetail ? (
                          <>
                            <td className="px-1 py-2">
                              <span className="text-xs text-slate-400">{m._cv !== '' ? parseFloat(m._cv).toFixed(3) : '-'}</span>
                            </td>
                            <td className="px-1 py-2">
                              <span className="text-xs text-slate-400">{m._ov !== '' ? parseFloat(m._ov).toFixed(3) : '-'}</span>
                            </td>
                          </>
                        ) : null}
                        <td className={`px-2 py-2 ${m._fs !== '' && parseFloat(m._fs) >= 1.0 ? 'text-emerald-700' : m._fs !== '' ? 'text-rose-600' : ''}`}>
                          <input type="number" step="0.001" min="0" max="5" value={m._fs}
                            onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _fs: e.target.value }; setMembers(cp); }}
                            className="w-18 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200 font-medium" />
                        </td>
                        <td className="px-2 py-2">
                          <input type="number" step="0.001" min="0" max="5" value={m._ncb}
                            onChange={(e) => { const cp = [...members]; cp[i] = { ...cp[i], _ncb: e.target.value }; setMembers(cp); }}
                            className="w-18 rounded-lg border border-slate-200 px-1.5 py-1 text-sm outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-200" />
                        </td>
                        {showDetail ? (
                          <>
                            <td className="px-1 py-2">
                              <span className="text-xs text-slate-400">{m._cdv !== '' ? parseFloat(m._cdv).toFixed(3) : '-'}</span>
                            </td>
                            <td className="px-1 py-2">
                              <span className="text-xs text-slate-400">{m._cs !== '' ? parseFloat(m._cs).toFixed(2) : '-'}</span>
                            </td>
                          </>
                        ) : null}
                      </>
                    ) : null}
                    <td className="px-4 py-2">
                      {recalcing === m.userId ? (
                        <span className="text-xs text-slate-400">计算中...</span>
                      ) : m.calcStatus === 'calculated' ? (
                        <button
                          onClick={() => handleRecalc(m.userId)}
                          className="text-xs text-emerald-600 hover:text-emerald-800 hover:underline cursor-pointer"
                          title="点击重新计算"
                        >
                          已计算
                        </button>
                      ) : m.calcStatus === 'filled' ? (
                        <button
                          onClick={() => handleRecalc(m.userId)}
                          className="text-xs text-sky-600 hover:text-sky-800 hover:underline cursor-pointer"
                          title="点击触发计算"
                        >
                          待计算
                        </button>
                      ) : m.calcStatus === 'archived' ? (
                        <span className="text-xs text-slate-400">已归档</span>
                      ) : (
                        <span className="text-xs text-slate-300">未导入</span>
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
              {saving ? '保存中...' : editCalc ? '保存全部修改' : '保存'}
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
