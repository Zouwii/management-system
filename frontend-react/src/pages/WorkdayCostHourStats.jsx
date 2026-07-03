import { useEffect, useState, useCallback, useMemo } from 'react';
import ManagerLayout from '../layouts/ManagerLayout';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import {
  fetchWorkdayCosthourTeamSummary,
  fetchWorkdayCosthourDeptAggregate,
  fetchWorkdayCosthourTaskDetail,
  fetchWorkdayCosthourMemberSummary,
  fetchWorkdayCosthourProjectNameDetail,
  fetchWorkdays,
} from '../api/dashboard';

// ── 动态季度选项（基于当前年份） ──

function generateQuarterOptions() {
  const now = new Date();
  const year = now.getFullYear();
  const options = [];
  for (let q = 1; q <= 4; q++) {
    const startMonth = (q - 1) * 3 + 1;
    const endMonth = startMonth + 2;
    const start = `${year}-${String(startMonth).padStart(2, '0')}-01T00:00:00`;
    const endDate = new Date(year, endMonth, 0);
    const end = `${year}-${String(endMonth).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}T23:59:59`;
    options.push({
      value: `q${q}`,
      label: `${year}年 Q${q} (${startMonth}月-${endMonth}月)`,
      start,
      end,
    });
  }
  options.push({
    value: 'year',
    label: `${year}年 全年`,
    start: `${year}-01-01T00:00:00`,
    end: `${year}-12-31T23:59:59`,
  });
  return options;
}

const QUARTER_OPTIONS = generateQuarterOptions();

// ── 辅助函数 ──

function formatDays(hours) {
  const n = Number(hours);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(2);
}

// ── 小组选择器 ──

function TeamSelector({ teams = [], selectedTeamId, onSelect }) {
  return (
    <div className="flex items-center gap-2">
      <label className="whitespace-nowrap text-sm font-medium text-slate-600">当前小组</label>
      <select
        value={selectedTeamId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none focus:border-slate-400"
      >
        {teams.map((t) => (
          <option key={t.teamId} value={t.teamId}>{t.teamName}</option>
        ))}
      </select>
    </div>
  );
}

// ── 饼图（实心 + 引线标注，复用于项目类型和任务类型） ──

const PIE_COLORS = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'];

function ProjectTypePieChart({ data = {}, title = '工时占比' }) {
  const entries = Object.entries(data).filter(([, v]) => v.hours > 0);
  if (entries.length === 0) return null;

  const total = entries.reduce((s, [, v]) => s + v.hours, 0);
  const cx = 150, cy = 110, r = 75;

  function polar(angleDeg, radius = r) {
    const rad = (angleDeg - 90) * Math.PI / 180;
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  }

  function arcPath(startDeg, endDeg) {
    const s = polar(startDeg);
    const e = polar(endDeg);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y} Z`;
  }

  let cumulative = 0;
  const slices = entries.map(([name, v]) => {
    const pct = v.hours / total;
    const startDeg = cumulative * 360;
    cumulative += pct;
    const endDeg = cumulative * 360;
    const midDeg = (startDeg + endDeg) / 2;
    const inner = polar(midDeg, r);
    const outer = polar(midDeg, r + 28);
    const isRight = midDeg <= 90 || midDeg >= 270;
    const labelX = isRight ? outer.x + 10 : outer.x - 10;
    return { name, pct, path: arcPath(startDeg, endDeg), inner, outer, labelX, labelY: outer.y, textAnchor: isRight ? 'start' : 'end' };
  });

  return (
    <div className="mt-2">
      <h4 className="text-sm font-semibold text-gray-600 mb-2">{title}</h4>
      <svg viewBox="0 0 320 220" className="w-full max-w-[320px] mx-auto" style={{ overflow: 'visible' }}>
        {slices.map((seg, i) => (
          <g key={seg.name}>
            <path d={seg.path} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="#fff" strokeWidth="1.5" />
            <polyline
              points={`${seg.inner.x},${seg.inner.y} ${seg.outer.x},${seg.outer.y} ${seg.labelX},${seg.labelY}`}
              fill="none" stroke={PIE_COLORS[i % PIE_COLORS.length]} strokeWidth="1.2"
            />
            <text
              x={seg.labelX + (seg.textAnchor === 'start' ? 4 : -4)}
              y={seg.labelY + 4}
              textAnchor={seg.textAnchor}
              fill="#334155"
              style={{ fontSize: '11px', fontWeight: 500 }}
            >
              {seg.name}
            </text>
            <text
              x={seg.labelX + (seg.textAnchor === 'start' ? 4 : -4)}
              y={seg.labelY + 17}
              textAnchor={seg.textAnchor}
              fill="#64748b"
              style={{ fontSize: '10px' }}
            >
              {(seg.pct * 100).toFixed(0)}%
            </text>
          </g>
        ))}
      </svg>
      <div className="flex justify-center gap-4 mt-3 text-xs">
        {slices.map((seg, i) => (
          <div key={seg.name} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
            <span className="text-slate-500">{seg.name}</span>
            <span className="font-semibold text-slate-700">{(seg.pct * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 车型工时柱状图（纯 SVG） ──

const BAR_COLORS = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

function VehicleBarChart({ data = {} }) {
  const entries = Object.entries(data)
    .filter(([, v]) => v.hours > 0)
    .sort((a, b) => b[1].hours - a[1].hours);
  if (entries.length === 0) return null;

  const maxHours = Math.max(...entries.map(([, v]) => v.hours));
  const step = 30;
  const yMax = Math.ceil(maxHours / step) * step;
  const ticks = Array.from({ length: yMax / step + 1 }, (_, i) => i * step);
  const vbW = 260, vbH = 200;
  const padL = 40, padR = 10, padT = 8, padB = 40;
  const chartW = vbW - padL - padR;
  const chartH = vbH - padT - padB;
  const barGap = 8;
  const barW = (chartW - barGap * (entries.length - 1)) / entries.length;

  return (
    <div className="mt-2">
      <h4 className="text-sm font-semibold text-gray-600 mb-2">车型工时分布</h4>
      <svg viewBox={`0 0 ${vbW} ${vbH}`} className="w-full max-w-[260px] mx-auto">
        {/* Y 轴 */}
        <line x1={padL} y1={padT} x2={padL} y2={padT + chartH} stroke="#cbd5e1" strokeWidth="1" />
        {/* X 轴 */}
        <line x1={padL} y1={padT + chartH} x2={vbW - padR} y2={padT + chartH} stroke="#cbd5e1" strokeWidth="1" />
        {/* Y 轴刻度线 */}
        {ticks.map((val) => {
          const y = padT + chartH - (val / yMax) * chartH;
          return (
            <g key={val}>
              <line x1={padL} y1={y} x2={vbW - padR} y2={y} stroke="#e2e8f0" strokeWidth="0.5" />
              <text x={padL - 6} y={y + 4} textAnchor="end" fill="#94a3b8" style={{ fontSize: '9px' }}>
                {val}
              </text>
            </g>
          );
        })}
        {/* 柱 */}
        {entries.map(([name, v], i) => {
          const x = padL + i * (barW + barGap);
          const h = (v.hours / yMax) * chartH;
          const y = padT + chartH - h;
          return (
            <g key={name}>
              <rect
                x={x} y={y} width={barW} height={h} rx="2"
                fill={BAR_COLORS[i % BAR_COLORS.length]}
              />
              <text
                x={x + barW / 2} y={vbH - 10}
                textAnchor="middle" fill="#475569"
                style={{ fontSize: '10px' }}
              >
                {name.length > 4 ? name.slice(0, 4) + '…' : name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── 双柱对比图（工时 + 事项数） ──

function DualBarChart({ data = {}, title = '' }) {
  const entries = Object.entries(data)
    .filter(([, v]) => v.hours > 0 || v.count > 0);
  if (entries.length === 0) return null;

  const maxHours = Math.max(...entries.map(([, v]) => v.hours), 1);
  const maxCount = Math.max(...entries.map(([, v]) => v.count), 1);
  const vbW = 280, vbH = 180;
  const padL = 45, padR = 10, padT = 10, padB = 36;
  const chartW = vbW - padL - padR;
  const chartH = vbH - padT - padB;
  const groupGap = 20;
  const barGroupW = (chartW - groupGap * (entries.length - 1)) / entries.length;
  const barW = (barGroupW - 4) / 2;

  // Y 轴刻度
  const hourStep = Math.ceil(maxHours / 30) * 30 > 0 ? 30 : 10;
  const hourMax = Math.ceil(maxHours / hourStep) * hourStep;
  const countMax = Math.ceil(maxCount / 50) * 50 || 50;

  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-600 mb-2">{title}</h4>
      <svg viewBox={`0 0 ${vbW} ${vbH}`} className="w-full max-w-[280px] mx-auto">
        {/* Y 轴 */}
        <line x1={padL} y1={padT} x2={padL} y2={padT + chartH} stroke="#cbd5e1" strokeWidth="1" />
        {/* X 轴 */}
        <line x1={padL} y1={padT + chartH} x2={vbW - padR} y2={padT + chartH} stroke="#cbd5e1" strokeWidth="1" />
        {/* Y 轴刻度 */}
        {Array.from({ length: 6 }, (_, i) => {
          const val = (hourMax / 5) * i;
          const y = padT + chartH - (val / hourMax) * chartH;
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={vbW - padR} y2={y} stroke="#e2e8f0" strokeWidth="0.5" />
              <text x={padL - 6} y={y + 4} textAnchor="end" fill="#94a3b8" style={{ fontSize: '9px' }}>
                {val.toFixed(0)}
              </text>
            </g>
          );
        })}
        {/* 柱 */}
        {entries.map(([name, v], i) => {
          const gx = padL + i * (barGroupW + groupGap);
          const hH = (v.hours / hourMax) * chartH;
          const hC = (v.count / countMax) * chartH;
          return (
            <g key={name}>
              <rect x={gx} y={padT + chartH - hH} width={barW} height={hH} rx="2" fill="#3b82f6" />
              <rect x={gx + barW + 4} y={padT + chartH - hC} width={barW} height={hC} rx="2" fill="#10b981" />
              <text x={gx + barW + 2} y={vbH - 10} textAnchor="middle" fill="#475569" style={{ fontSize: '10px' }}>
                {name.length > 4 ? name.slice(0, 4) + '…' : name}
              </text>
            </g>
          );
        })}
      </svg>
      {/* 图例 */}
      <div className="flex justify-center gap-4 mt-2 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-blue-500" />
          <span className="text-slate-500">占用工时（天）</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-blue-400" />
          <span className="text-slate-500">处理事项</span>
        </div>
      </div>
    </div>
  );
}

// ── 有效工时组别管理表 ──

function EffectiveHourManageTable({ teams = [], selectedTeamId, onTeamChange, members = [], standardDays = 0, adjustments = {}, onAdjustmentChange }) {
  const selectedMembers = members.filter((m) => !selectedTeamId || m.teamId === selectedTeamId);

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-col items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-4 md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold text-slate-900">员工出勤表</h2>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600">
            季度标准：{formatDays(standardDays)}天
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="whitespace-nowrap text-sm font-medium text-slate-600">组别</label>
            <select
              value={selectedTeamId || ''}
              onChange={(e) => onTeamChange(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-slate-400"
            >
              {teams.map((team) => (
                <option key={team.teamId} value={team.teamId}>{team.teamName}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-white text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left font-medium">姓名</th>
              <th className="px-5 py-3 text-right font-medium">预期天数</th>
              <th className="px-5 py-3 text-right font-medium">实际天数</th>
              <th className="bg-sky-50 px-5 py-3 text-center font-medium text-sky-700">加班</th>
              <th className="bg-sky-50 px-5 py-3 text-center font-medium text-sky-700">请假</th>
              <th className="px-5 py-3 text-right font-medium">差额</th>
            </tr>
          </thead>
          <tbody>
            {selectedMembers.length === 0 ? (
              <tr><td className="px-5 py-4 text-slate-400" colSpan={6}>暂无数据</td></tr>
            ) : selectedMembers.map((member) => {
              const workday = Number(member.workdayCosthour || 0);
              const adjustment = adjustments[member.userId] || {};
              const overtime = Number(adjustment.overtimeDays || 0);
              const leave = Number(adjustment.leaveDays || 0);
              const standard = Number(standardDays || 0);
              const personalStandard = standard + overtime - leave;
              const diff = workday - personalStandard;
              return (
                <tr key={member.userId} className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50">
                  <td className="px-5 py-3 font-semibold text-slate-900">{member.userName}</td>
                  <td className="bg-slate-50/60 px-5 py-3 text-right tabular-nums text-slate-600">{formatDays(personalStandard)}</td>
                  <td className="bg-slate-50/60 px-5 py-3 text-right tabular-nums text-slate-600">{formatDays(workday)}</td>
                  <td className="bg-sky-50/60 px-5 py-3 text-center">
                    <input
                      type="number"
                      value={overtime}
                      step="0.5"
                      min="0"
                      onChange={(e) => onAdjustmentChange(member.userId, 'overtimeDays', e.target.value)}
                      className="w-24 rounded-xl border border-sky-200 bg-white px-3 py-2 text-center text-sm font-medium text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                    />
                  </td>
                  <td className="bg-sky-50/60 px-5 py-3 text-center">
                    <input
                      type="number"
                      value={leave}
                      step="0.5"
                      min="0"
                      onChange={(e) => onAdjustmentChange(member.userId, 'leaveDays', e.target.value)}
                      className="w-24 rounded-xl border border-sky-200 bg-white px-3 py-2 text-center text-sm font-medium text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                    />
                  </td>
                  <td className={`px-5 py-3 text-right font-semibold tabular-nums ${diff < 0 ? 'text-rose-700' : 'text-emerald-700'}`}>{formatDays(diff)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ── 小表组件（Section 1 的三列表格） ──

function SmallTable({ title, data = {} }) {
  const entries = Object.entries(data).sort((a, b) => (b[1].hours || 0) - (a[1].hours || 0));
  const totalHours = entries.reduce((s, [, v]) => s + (v.hours || 0), 0);

  if (entries.length === 0) {
    return (
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 text-left font-medium">{title}</th>
              <th className="px-4 py-3 text-right font-medium">工时（人/天）</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className="px-4 py-3 text-slate-400" colSpan={2}>暂无数据</td></tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-3 text-left font-medium">{title}</th>
            <th className="px-4 py-3 text-right font-medium">工时（人/天）</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, val]) => (
            <tr key={key} className="border-b border-slate-100 last:border-b-0">
              <td className="px-4 py-3 text-slate-700">{key}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">{formatDays(val.hours)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 bg-slate-50 font-semibold text-slate-900">
            <td className="px-4 py-3">总计</td>
            <td className="px-4 py-3 text-right tabular-nums">{formatDays(totalHours)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// ── 大表组件（Section 2 的表格） ──

function AggregateTable({ title, data = {} }) {
  const entries = Object.entries(data).sort((a, b) => (b[1].hours || 0) - (a[1].hours || 0));
  const totalHours = entries.reduce((s, [, v]) => s + (v.hours || 0), 0);
  const totalCount = entries.reduce((s, [, v]) => s + (v.count || 0), 0);

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-3 text-left font-medium">{title}</th>
            <th className="px-4 py-3 text-right font-medium">占用工时（天）</th>
            <th className="px-4 py-3 text-right font-medium">处理事项</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 ? (
            <tr><td className="px-4 py-3 text-slate-400" colSpan={3}>暂无数据</td></tr>
          ) : (
            entries.map(([key, val]) => (
              <tr key={key} className="border-b border-slate-100 last:border-b-0">
                <td className="px-4 py-3 text-slate-700">{key}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">{formatDays(val.hours)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">{val.count}</td>
              </tr>
            ))
          )}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 bg-slate-50 font-semibold text-slate-900">
            <td className="px-4 py-3">总计</td>
            <td className="px-4 py-3 text-right tabular-nums">{formatDays(totalHours)}</td>
            <td className="px-4 py-3 text-right tabular-nums">{totalCount}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// ── Section 3: 任务状态层级表格 ──

function TaskStatusTable({ details = [], summary = {} }) {
  if (!details.length) {
    return <div className="p-4 text-center text-slate-400">暂无数据</div>;
  }

  return (
    <div className="overflow-x-auto text-xs">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left font-medium">任务状态</th>
            <th className="px-3 py-2 text-right font-medium">占用工时（天）</th>
            <th className="px-3 py-2 text-right font-medium">处理事项</th>
          </tr>
        </thead>
        <tbody>
          {details.map((group) => (
            <>
              <tr key={group.projectType} className="border-b border-slate-100 bg-slate-50 font-semibold text-slate-900">
                <td className="px-3 py-2">{group.projectType}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatDays(group.totalHours)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{group.totalCount}</td>
              </tr>
              {(group.children || []).map((child) => (
                <tr key={`${group.projectType}-${child.taskType}`} className="border-b border-slate-100">
                  <td className="px-3 py-2 pl-7 text-slate-600">{child.taskType}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{formatDays(child.hours)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{child.count}</td>
                </tr>
              ))}
            </>
          ))}
          <tr className="border-t border-slate-200 bg-slate-50 font-semibold text-slate-900">
            <td className="px-3 py-2">总计</td>
            <td className="px-3 py-2 text-right tabular-nums">{formatDays(summary.totalHours)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{summary.totalCount}</td>
          </tr>
          <tr className="border-b border-slate-100">
            <td className="px-3 py-2 pl-7 text-slate-600">软件开发</td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600">{formatDays(summary['软件开发']?.hours)}</td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600">{summary['软件开发']?.count}</td>
          </tr>
          <tr>
            <td className="px-3 py-2 pl-7 text-slate-600">问题处理</td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600">{formatDays(summary['问题处理']?.hours)}</td>
            <td className="px-3 py-2 text-right tabular-nums text-slate-600">{summary['问题处理']?.count}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ── Section 4: 项目名称明细表（三个独立小表） ──

function ProjectTypeSubTable({ projectType, totalHours, projectNames = [] }) {
  // 过滤掉全0的
  const items = projectNames.filter((pn) => pn.totalHours > 0).sort((a, b) => (b.totalHours || 0) - (a.totalHours || 0));

  if (!items.length) {
    return (
      <div className="flex-1 min-w-[280px]">
        <h3 className="mb-2 text-base font-semibold text-slate-900">{projectType}</h3>
        <p className="text-sm text-slate-400">暂无数据</p>
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-[280px]">
      <h3 className="mb-2 text-base font-semibold text-slate-900">{projectType}</h3>
      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left font-medium">项目名称</th>
            <th className="px-3 py-2 text-right font-medium">工时</th>
            <th className="px-3 py-2 text-right font-medium">软件开发</th>
            <th className="px-3 py-2 text-right font-medium">问题处理</th>
          </tr>
        </thead>
        <tbody>
          {items.map((pn) => {
            const sw = pn.children.find((c) => c.taskType === '软件开发') || {};
            const issue = pn.children.find((c) => c.taskType === '问题处理') || {};
            return (
              <tr key={pn.projectName} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-700">{pn.projectName}</td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums text-slate-900">{formatDays(pn.totalHours)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-600">{formatDays(sw.hours || 0)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-600">{formatDays(issue.hours || 0)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 bg-slate-50 font-semibold text-slate-900">
            <td className="px-3 py-2">合计</td>
            <td className="px-3 py-2 text-right tabular-nums">{formatDays(totalHours)}</td>
            <td className="px-3 py-2 text-right tabular-nums">
              {formatDays(items.reduce((s, pn) => s + (pn.children.find((c) => c.taskType === '软件开发')?.hours || 0), 0))}
            </td>
            <td className="px-3 py-2 text-right tabular-nums">
              {formatDays(items.reduce((s, pn) => s + (pn.children.find((c) => c.taskType === '问题处理')?.hours || 0), 0))}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function ProjectNameDetailTable({ details = [] }) {
  if (!details.length) {
    return <div className="p-4 text-center text-slate-400">暂无数据</div>;
  }

  return (
    <div className="flex flex-col md:flex-row gap-6">
      {details.map((pt) => (
        <ProjectTypeSubTable
          key={pt.projectType}
          projectType={pt.projectType}
          totalHours={pt.totalHours}
          projectNames={pt.projectNames || []}
        />
      ))}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
//  主页面组件
// ════════════════════════════════════════════════════════════════

export default function WorkdayCostHourStats() {
  const [quarter, setQuarter] = useState('q1');
  const [selectedTeamId, setSelectedTeamId] = useState(null);
  const [manageTeamId, setManageTeamId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // 接口1：各小组汇总
  const [teamData, setTeamData] = useState({ timeRange: {}, total: {}, teams: [] });
  // 接口2：部门聚合
  const [deptData, setDeptData] = useState({ timeRange: {}, total: {}, byProjectType: {}, byVehicleType: {} });
  // 接口3：任务状态明细
  const [taskData, setTaskData] = useState({ timeRange: {}, total: {}, details: [], summary: {} });
  // 个人维度统计
  const [memberData, setMemberData] = useState({ timeRange: {}, total: {}, teams: [], members: [] });
  // 页面临时录入：加班/请假，不持久化
  const [memberAdjustments, setMemberAdjustments] = useState({});
  // 工作日数
  const [workdayCount, setWorkdayCount] = useState(null);
  // 项目名称明细
  const [projectNameData, setProjectNameData] = useState({ timeRange: {}, total: {}, details: [] });

  const quarterOption = useMemo(
    () => QUARTER_OPTIONS.find((q) => q.value === quarter) || QUARTER_OPTIONS[0],
    [quarter],
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const payload = { start_time: quarterOption.start, end_time: quarterOption.end };

    try {
      const [tRes, dRes, sRes, mRes, pnRes, wRes] = await Promise.all([
        fetchWorkdayCosthourTeamSummary(payload),
        fetchWorkdayCosthourDeptAggregate(payload),
        fetchWorkdayCosthourTaskDetail(payload),
        fetchWorkdayCosthourMemberSummary(payload),
        fetchWorkdayCosthourProjectNameDetail(payload),
        fetchWorkdays(payload),
      ]);
      const t = tRes?.data || {};
      setTeamData({ timeRange: t.timeRange || {}, total: t.total || {}, teams: t.teams || [] });
      if (!selectedTeamId && t.teams?.length) {
        setSelectedTeamId(t.teams[0].teamId);
      }

      const d = dRes?.data || {};
      setDeptData({ timeRange: d.timeRange || {}, total: d.total || {}, byProjectType: d.byProjectType || {}, byVehicleType: d.byVehicleType || {} });

      const s = sRes?.data || {};
      setTaskData({ timeRange: s.timeRange || {}, total: s.total || {}, details: s.details || [], summary: s.summary || {} });

      const pn = pnRes?.data || {};
      setProjectNameData({ timeRange: pn.timeRange || {}, total: pn.total || {}, details: pn.details || [] });

      const m = mRes?.data || {};
      const nextMemberData = { timeRange: m.timeRange || {}, total: m.total || {}, teams: m.teams || [], members: m.members || [] };
      setMemberData(nextMemberData);
      if (!manageTeamId && nextMemberData.teams?.length) {
        setManageTeamId(nextMemberData.teams[0].teamId);
      }

      const wd = wRes?.data?.workday_count ?? wRes?.data?.effective_workday_count ?? wRes?.data?.workdays ?? null;
      setWorkdayCount(wd);
    } catch (err) {
      console.error('工作日耗时数据加载失败:', err);
      setError(err?.message || '数据加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [quarterOption, selectedTeamId, manageTeamId]);

  // 首次加载
  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleQuery = useCallback(() => {
    loadAll();
  }, [loadAll]);

  const handleAdjustmentChange = useCallback((userId, field, value) => {
    setMemberAdjustments((prev) => ({
      ...prev,
      [userId]: {
        ...(prev[userId] || {}),
        [field]: value,
      },
    }));
  }, []);

  const currentTeam = useMemo(
    () => teamData.teams.find((t) => t.teamId === selectedTeamId) || teamData.teams[0] || {},
    [teamData.teams, selectedTeamId],
  );

  return (
    <ManagerLayout>
      <SectionTitle
        title="工作日耗时"
      />

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
          {error}
          <button
            type="button"
            onClick={loadAll}
            className="ml-4 underline hover:text-rose-900"
          >
            重试
          </button>
        </div>
      ) : null}

      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="text-lg font-semibold text-slate-900">筛选时间</div>
          <div className="flex w-full flex-wrap items-center gap-3 md:w-auto">
            <label className="flex items-center gap-2 whitespace-nowrap text-sm text-slate-600">
              <span className="shrink-0">统计季度</span>
              <select
                value={quarter}
                onChange={(e) => setQuarter(e.target.value)}
                className="w-[220px] rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400"
              >
                {QUARTER_OPTIONS.map((q) => (
                  <option key={q.value} value={q.value}>{q.label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleQuery}
              disabled={loading}
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {loading ? '查询中...' : '查询'}
            </button>
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        {loading ? (
          <div className="py-12 text-center text-slate-400">加载中...</div>
        ) : (
          <>
            {/* ═══════ Effective Hour Management: 个人维度有效工时 ═══════ */}
            <EffectiveHourManageTable
              teams={memberData.teams.length ? memberData.teams : teamData.teams}
              selectedTeamId={manageTeamId}
              onTeamChange={setManageTeamId}
              members={memberData.members}
              standardDays={workdayCount || 0}
              adjustments={memberAdjustments}
              onAdjustmentChange={handleAdjustmentChange}
            />

            <Card className="overflow-hidden p-0">
              <div className="flex flex-col items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-4 md:flex-row md:items-center">
                <h2 className="text-lg font-semibold text-slate-900">小组数据看板</h2>
                <div className="flex items-center gap-2">
                  <TeamSelector
                    teams={teamData.teams}
                    selectedTeamId={selectedTeamId}
                    onSelect={setSelectedTeamId}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-6">
                <div className="flex flex-col">
                  <SmallTable title="项目类型" data={currentTeam.byProjectType || {}} />
                  <div className="mt-auto pt-6">
                    <ProjectTypePieChart data={currentTeam.byProjectType || {}} title="项目类型工时占比" />
                  </div>
                </div>
                <div className="flex flex-col">
                  <SmallTable title="车型" data={currentTeam.byVehicleType || {}} />
                  <div className="mt-auto pt-6">
                    <VehicleBarChart data={currentTeam.byVehicleType || {}} />
                  </div>
                </div>
                <div className="flex flex-col">
                  <SmallTable title="任务类型" data={currentTeam.byTaskType || {}} />
                  <div className="mt-auto pt-6">
                    <ProjectTypePieChart data={currentTeam.byTaskType || {}} title="任务类型工时占比" />
                  </div>
                </div>
              </div>
            </Card>

            <Card className="overflow-hidden p-0">
              <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
                <h2 className="text-lg font-semibold text-slate-900">
                  部门汇总数据（导航组 + 对接组）· {quarterOption.label.split('(')[0].trim()}
                  {workdayCount != null ? ` (共计${workdayCount}天)` : ''}
                </h2>
              </div>
              <div className="grid gap-8 p-6 lg:grid-cols-2">
                <div className="flex flex-col">
                  <AggregateTable title="项目类型" data={deptData.byProjectType} />
                  <div className="mt-auto pt-6">
                    <DualBarChart data={deptData.byProjectType} title="项目类型 - 工时与事项数" />
                  </div>
                </div>
                <div className="flex flex-col">
                  <AggregateTable title="车型" data={deptData.byVehicleType} />
                  <div className="mt-auto pt-6">
                    <DualBarChart data={deptData.byVehicleType} title="车型 - 工时与事项数" />
                  </div>
                </div>
              </div>
              <div className="border-t border-slate-200">
                <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
                  <h3 className="text-base font-semibold text-slate-900">任务状态统计</h3>
                </div>
                <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(260px,0.6fr)]">
                  <TaskStatusTable details={taskData.details} summary={taskData.summary} />
                  <div className="flex items-center justify-center">
                    <ProjectTypePieChart
                      data={{
                        '软件开发': taskData.summary['软件开发'] || { hours: 0, count: 0 },
                        '问题处理': taskData.summary['问题处理'] || { hours: 0, count: 0 },
                      }}
                      title="软件开发 / 问题处理工时占比"
                    />
                  </div>
                </div>
              </div>
              <div>
                <div className="bg-slate-50 px-5 py-4">
                  <h3 className="text-base font-semibold text-slate-900">项目类型统计</h3>
                </div>
                <div className="p-6 pt-4">
                  <ProjectNameDetailTable details={projectNameData.details} />
                </div>
              </div>
            </Card>
          </>
        )}
      </div>
    </ManagerLayout>
  );
}
