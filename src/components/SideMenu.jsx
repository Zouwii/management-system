import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import Card from './Card';
import { useAuthStore } from '../store/authStore';

export default function SideMenu({ title, subtitle, menus, theme = 'dark', note, actionLabel = '切换登录角色', actionTo = '/login' }) {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const activeClass = theme === 'dark' ? 'bg-slate-900 text-white' : 'bg-blue-600 text-white';
  const logoClass = theme === 'dark' ? 'bg-slate-900 text-white' : 'bg-blue-600 text-white';
  const noteClass = theme === 'dark'
    ? 'border-slate-200 bg-slate-50 text-slate-500'
    : 'border-blue-100 bg-blue-50 text-blue-800';
  const collapseStorageKey = `side-menu-collapsed:${theme}:${title}`;

  function handleSwitchRole() {
    logout();
    navigate(actionTo, { replace: true });
  }

  const groupedMenus = useMemo(() => menus.reduce((acc, item) => {
    const section = item.section ?? '功能导航';

    if (!acc[section]) {
      acc[section] = [];
    }

    acc[section].push(item);
    return acc;
  }, {}), [menus]);

  const defaultCollapsedSections = useMemo(() => {
    const nextState = {};

    Object.entries(groupedMenus).forEach(([section, items]) => {
      const hasActiveItem = items.some((item) => item.to === location.pathname);
      nextState[section] = !hasActiveItem;
    });

    return nextState;
  }, [groupedMenus, location.pathname]);

  const [collapsedSections, setCollapsedSections] = useState(() => {
    try {
      const savedState = window.localStorage.getItem(collapseStorageKey);
      return savedState ? JSON.parse(savedState) : {};
    } catch {
      return {};
    }
  });
  const resolvedCollapsedSections = useMemo(
    () => ({ ...defaultCollapsedSections, ...collapsedSections }),
    [collapsedSections, defaultCollapsedSections],
  );

  useEffect(() => {
    window.localStorage.setItem(collapseStorageKey, JSON.stringify(collapsedSections));
  }, [collapseStorageKey, collapsedSections]);

  function toggleSection(section) {
    setCollapsedSections((prev) => ({
      ...prev,
      [section]: !resolvedCollapsedSections[section],
    }));
  }

  return (
    <Card className="sticky top-6 p-5">
      <div className="flex items-center gap-3 border-b border-slate-200 pb-5">
        <div className={`flex h-12 w-12 items-center justify-center rounded-2xl font-semibold ${logoClass}`}>
          {theme === 'dark' ? 'BD' : '李'}
        </div>
        <div>
          <div className="font-semibold text-slate-900">{title}</div>
          <div className="text-sm text-slate-500">{subtitle}</div>
        </div>
      </div>
      <div className="mt-5 space-y-4">
        {Object.entries(groupedMenus).map(([section, items]) => (
          <div key={section}>
            <button
              type="button"
              onClick={() => toggleSection(section)}
              className="mb-2 flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 hover:bg-slate-50"
            >
              <span>{section}</span>
              <span className={`text-slate-400 transition-transform ${resolvedCollapsedSections[section] ? '' : 'rotate-90'}`}>
                ›
              </span>
            </button>
            {!resolvedCollapsedSections[section] ? (
              <div className="space-y-2">
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => `block rounded-2xl px-4 py-3 text-sm font-medium ${isActive ? activeClass : 'text-slate-700 hover:bg-slate-50'}`}
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div className={`mt-8 rounded-2xl border p-4 ${noteClass}`}>
        <div className="text-sm font-medium text-slate-900">权限提示</div>
        <div className="mt-2 text-sm leading-6">{note}</div>
      </div>
      <button
        type="button"
        onClick={handleSwitchRole}
        className="mt-4 block rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {actionLabel}
      </button>
    </Card>
  );
}
