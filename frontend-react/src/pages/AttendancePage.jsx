import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import ManagerLayout from '../layouts/ManagerLayout';
import {
  fetchAttendance,
  fetchWorkdayCosthourMemberSummary,
  fetchWorkdays,
  saveAttendance,
} from '../api/dashboard';
import { AttendanceTable } from './WorkdayCostHourStats';

function generateQuarterOptions() {
  const now = new Date();
  const year = now.getFullYear();

  return Array.from({ length: 4 }, (_, index) => {
    const quarter = index + 1;
    const startMonth = index * 3 + 1;
    const endMonth = startMonth + 2;
    const endDate = new Date(year, endMonth, 0);

    return {
      value: `q${quarter}`,
      label: `${year}年 Q${quarter} (${startMonth}月-${endMonth}月)`,
      start: `${year}-${String(startMonth).padStart(2, '0')}-01T00:00:00`,
      end: `${year}-${String(endMonth).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}T23:59:59`,
    };
  });
}

const QUARTER_OPTIONS = generateQuarterOptions();

export default function AttendancePage() {
  const currentQuarter = `q${Math.floor(new Date().getMonth() / 3) + 1}`;
  const [quarter, setQuarter] = useState(currentQuarter);
  const [selectedTeamId, setSelectedTeamId] = useState(null);
  const [memberData, setMemberData] = useState({ teams: [], members: [] });
  const [adjustments, setAdjustments] = useState({});
  const [standardDays, setStandardDays] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saveMessage, setSaveMessage] = useState(null);

  const quarterOption = useMemo(
    () => QUARTER_OPTIONS.find((option) => option.value === quarter) || QUARTER_OPTIONS[0],
    [quarter],
  );

  const loadAttendance = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSaveMessage(null);
    const payload = { start_time: quarterOption.start, end_time: quarterOption.end };

    try {
      const [memberResponse, workdayResponse, attendanceResponse] = await Promise.all([
        fetchWorkdayCosthourMemberSummary(payload),
        fetchWorkdays(payload),
        fetchAttendance(payload),
      ]);
      const memberResult = memberResponse?.data || {};
      const teams = memberResult.teams || [];
      const members = memberResult.members || [];
      setMemberData({ teams, members });
      setSelectedTeamId((current) => (
        teams.some((team) => team.teamId === current) ? current : teams[0]?.teamId ?? null
      ));

      const workdayResult = workdayResponse?.data || {};
      setStandardDays(
        workdayResult.workday_count
        ?? workdayResult.effective_workday_count
        ?? workdayResult.workdays
        ?? 0,
      );
      const savedAttendance = new Map(
        (attendanceResponse?.data?.records || []).map((record) => [String(record.user_id), record]),
      );
      const nextAdjustments = {};
      members.forEach((member) => {
        const record = savedAttendance.get(String(member.userId));
        nextAdjustments[member.userId] = {
          overtimeDays: record?.overtime_days ?? 0,
          leaveDays: record?.leave_days ?? 0,
          holidayDays: record?.statutory_holiday_days ?? 0,
        };
      });
      setAdjustments(nextAdjustments);
    } catch (loadError) {
      console.error('出勤表数据加载失败:', loadError);
      setError(loadError?.message || '出勤表数据加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [quarterOption]);

  useEffect(() => {
    loadAttendance();
  }, [loadAttendance]);

  useEffect(() => {
    if (!saveMessage) return undefined;
    const timer = window.setTimeout(() => setSaveMessage(null), 3000);
    return () => window.clearTimeout(timer);
  }, [saveMessage]);

  const handleAdjustmentChange = useCallback((userId, field, value) => {
    setAdjustments((current) => ({
      ...current,
      [userId]: {
        ...(current[userId] || {}),
        [field]: value,
      },
    }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveMessage(null);
    const records = memberData.members.map((member) => {
      const adjustment = adjustments[member.userId] || {};
      return {
        user_id: member.userId,
        user_name: member.userName,
        team_id: member.teamId,
        overtime_days: Number(adjustment.overtimeDays || 0),
        leave_days: Number(adjustment.leaveDays || 0),
        statutory_holiday_days: Number(adjustment.holidayDays || 0),
        effective_work_days: Math.max(
          0,
          Number(standardDays || 0) - Number(adjustment.holidayDays || 0),
        ),
      };
    });

    try {
      const response = await saveAttendance({
        start_time: quarterOption.start,
        records,
      });
      if (response?.code === 200 || response?.data) {
        setSaveMessage({
          type: 'success',
          text: `已保存 ${response?.data?.saved_count ?? records.length} 条记录`,
        });
      } else {
        setSaveMessage({ type: 'error', text: response?.error || response?.message || '保存失败' });
      }
    } catch (saveError) {
      setSaveMessage({ type: 'error', text: saveError?.message || '保存失败' });
    } finally {
      setSaving(false);
    }
  }, [adjustments, memberData.members, quarterOption, standardDays]);

  return (
    <ManagerLayout>
      <SectionTitle title="出勤表" />

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
          {error}
          <button type="button" onClick={loadAttendance} className="ml-4 underline hover:text-rose-900">
            重试
          </button>
        </div>
      ) : null}

      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="text-lg font-semibold text-slate-900">筛选时间</div>
          <div className="flex w-full flex-wrap items-center gap-3 md:w-auto">
            <label className="flex w-full items-center gap-2 whitespace-nowrap text-sm text-slate-600 sm:w-auto">
              <span className="shrink-0">统计季度</span>
              <select
                value={quarter}
                onChange={(event) => setQuarter(event.target.value)}
                className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-400 sm:w-[220px] sm:flex-none"
              >
                {QUARTER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={loadAttendance}
              disabled={loading}
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {loading ? '查询中...' : '查询'}
            </button>
          </div>
        </div>
      </Card>

      {loading ? (
        <div className="py-12 text-center text-slate-400">加载中...</div>
      ) : (
        <AttendanceTable
          teams={memberData.teams}
          selectedTeamId={selectedTeamId}
          onTeamChange={setSelectedTeamId}
          members={memberData.members}
          standardDays={standardDays}
          adjustments={adjustments}
          onAdjustmentChange={handleAdjustmentChange}
          onSave={handleSave}
          saving={saving}
        />
      )}

      {saveMessage ? (
        <div className={`rounded-xl px-4 py-2 text-sm font-medium ${
          saveMessage.type === 'success'
            ? 'bg-emerald-50 text-emerald-700'
            : 'bg-rose-50 text-rose-700'
        }`}>
          {saveMessage.text}
        </div>
      ) : null}
    </ManagerLayout>
  );
}
