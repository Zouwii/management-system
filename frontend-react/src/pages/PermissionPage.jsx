import { useEffect, useState } from 'react';
import { fetchPermissionMatrix, fetchTeams } from '../api/dashboard';
import Card from '../components/Card';
import SectionTitle from '../components/SectionTitle';
import { PAGE_PERMISSION_CODES } from '../constants/permissionCodes';
import ManagerLayout from '../layouts/ManagerLayout';

const PERMISSION_LABEL_MAP = {
  [PAGE_PERMISSION_CODES.DEPARTMENT_OVERVIEW]: '部门总览',
  [PAGE_PERMISSION_CODES.NAV_TEAM_DETAIL]: '导航组',
  [PAGE_PERMISSION_CODES.INTEGRATION_TEAM_DETAIL]: '对接组',
  [PAGE_PERMISSION_CODES.PERSONAL_HOURS]: '工时管理',
  [PAGE_PERMISSION_CODES.PERFORMANCE]: '绩效管理',
  [PAGE_PERMISSION_CODES.AI_ANALYSIS]: 'AI助理',
  [PAGE_PERMISSION_CODES.PERMISSIONS]: '权限管理',
};

export default function PermissionPage() {
  const [accounts, setAccounts] = useState([]);
  const [visiblePasswords, setVisiblePasswords] = useState({});
  const [roleFilter, setRoleFilter] = useState('全部角色');
  const [teamFilter, setTeamFilter] = useState('全部团队');
  const [teamOptions, setTeamOptions] = useState(['全部团队']);
  const [copyMessage, setCopyMessage] = useState('');

  useEffect(() => {
    let active = true;

    fetchPermissionMatrix().then((response) => {
      if (active) {
        setAccounts(response.data ?? []);
      }
    });

    fetchTeams().then((res) => {
      if (active) {
        const list = (res?.data?.teams || []).map((t) => t.label);
        setTeamOptions(['全部团队', ...list]);
      }
    }).catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  const filteredAccounts = accounts
    .filter((item) => roleFilter === '全部角色' || item.roleLabel === roleFilter)
    .filter((item) => teamFilter === '全部团队' || item.team === teamFilter);

  const roleOptions = ['全部角色', ...Array.from(new Set(accounts.map((item) => item.roleLabel)))];

  async function handleCopy(value, label) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyMessage(`已复制${label}。`);
    } catch {
      setCopyMessage(`复制${label}失败。`);
    }
  }

  function getRoleTagClass(roleLabel) {
    if (roleLabel === '管理员') {
      return 'border-slate-900 bg-slate-900 text-white';
    }

    if (roleLabel === '主管') {
      return 'border-amber-200 bg-amber-50 text-amber-800';
    }

    return 'border-sky-100 bg-sky-50 text-sky-700';
  }

  return (
    <ManagerLayout>
      <SectionTitle
        title="权限管理"
        desc="仅展示当前注册账号、登录密码和对应权限，用于快速核对权限配置。"
        right={(
          <div className="flex gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">当前注册账号 {accounts.length} 个</div>
          </div>
        )}
      />
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-lg font-semibold">已注册账号</div>
              <div className="mt-1 text-sm text-slate-500">默认隐藏登录密码，可查看、复制账号和密码，并按角色或团队快速筛选。</div>
            </div>
            <div className="grid gap-3 xl:grid-cols-2">
              <select
                value={roleFilter}
                onChange={(event) => setRoleFilter(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
              >
                {roleOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <select
                value={teamFilter}
                onChange={(event) => setTeamFilter(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none"
              >
                {teamOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </div>
          </div>
          {copyMessage ? (
            <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
              {copyMessage}
            </div>
          ) : null}
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">账号</th>
                <th className="px-5 py-4 text-left font-medium">姓名</th>
                <th className="px-5 py-4 text-left font-medium">角色</th>
                <th className="px-5 py-4 text-left font-medium">所属团队</th>
                <th className="px-5 py-4 text-left font-medium">数据范围</th>
                <th className="px-5 py-4 text-left font-medium">登录密码</th>
                <th className="px-5 py-4 text-left font-medium">对应权限</th>
              </tr>
            </thead>
            <tbody>
              {filteredAccounts.map((item, index) => (
                <tr key={item.account} className={index !== filteredAccounts.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-5 py-4 font-medium text-slate-900">
                    <div className="flex items-center gap-3">
                      <span>{item.account}</span>
                      <button
                        type="button"
                        onClick={() => handleCopy(item.account, `${item.account} 账号`)}
                        className="text-xs text-slate-400 hover:text-slate-700"
                        title="复制账号"
                      >
                        复制
                      </button>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-slate-600">{item.name}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${getRoleTagClass(item.roleLabel)}`}>
                      {item.roleLabel}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-slate-600">{item.team}</td>
                  <td className="px-5 py-4 text-slate-600">{item.dataScopeLabel}</td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-slate-900">
                        {visiblePasswords[item.account] ? item.password : '••••••'}
                      </span>
                      <button
                        type="button"
                        onClick={() => setVisiblePasswords((prev) => ({
                          ...prev,
                          [item.account]: !prev[item.account],
                        }))}
                        className="text-xs text-slate-400 hover:text-slate-700"
                      >
                        {visiblePasswords[item.account] ? '隐藏密码' : '查看密码'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCopy(item.password, `${item.account} 密码`)}
                        className="text-xs text-slate-400 hover:text-slate-700"
                        title="复制密码"
                      >
                        复制
                      </button>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex max-w-[420px] flex-wrap gap-2">
                      {item.permissionCodes
                        .filter((code) => PERMISSION_LABEL_MAP[code])
                        .map((code) => (
                        <span key={code} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700">
                          {PERMISSION_LABEL_MAP[code]}
                        </span>
                        ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </ManagerLayout>
  );
}
