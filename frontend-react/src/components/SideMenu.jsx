import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import Card from './Card';
import { useAuthStore } from '../store/authStore';

export default function SideMenu({
  title,
  subtitle,
  menus,
  theme = 'dark',
  logoSrc,
  logoAlt = '平台Logo',
  note,
  actionLabel = '切换登录角色',
  actionTo = '/login',
  collapsed = false,
  onToggleCollapse,
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const activeClass = theme === 'dark'
    ? 'bg-slate-900 text-white shadow-[0_10px_24px_-16px_rgba(15,23,42,0.8)]'
    : 'bg-gradient-to-r from-sky-500 to-cyan-500 text-white shadow-[0_12px_24px_-16px_rgba(14,165,233,0.9)]';
  const logoClass = theme === 'dark'
    ? 'bg-slate-900 text-white shadow-[0_14px_28px_-18px_rgba(15,23,42,0.8)]'
    : 'bg-gradient-to-br from-sky-500 via-cyan-400 to-emerald-400 text-white shadow-[0_18px_36px_-18px_rgba(6,182,212,0.8)]';
  const noteClass = theme === 'dark'
    ? 'border-slate-200/80 bg-slate-50/90 text-slate-500'
    : 'border-sky-100 bg-[linear-gradient(135deg,rgba(224,242,254,0.9),rgba(236,253,245,0.95))] text-sky-900';
  const containerClass = theme === 'dark'
    ? 'sticky top-6 border-slate-200/80 bg-white/88'
    : 'sticky top-6 border-sky-100/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(240,249,255,0.92))]';
  const actionButtonClass = theme === 'dark'
    ? 'mt-4 block rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center text-sm font-medium text-slate-700 hover:bg-slate-50'
    : 'mt-4 block rounded-2xl border border-sky-100 bg-white/90 px-4 py-3 text-center text-sm font-medium text-sky-700 shadow-[0_10px_24px_-20px_rgba(14,165,233,0.9)] hover:bg-sky-50';
  const sectionButtonClass = theme === 'dark'
    ? 'mb-3 flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-semibold text-slate-900 shadow-[0_8px_20px_-18px_rgba(15,23,42,0.35)] hover:bg-white'
    : 'mb-3 flex w-full items-center justify-between rounded-2xl border border-sky-100 bg-[linear-gradient(135deg,rgba(239,246,255,0.95),rgba(236,253,245,0.9))] px-4 py-3 text-left text-sm font-semibold text-sky-950 shadow-[0_12px_24px_-18px_rgba(14,165,233,0.35)] hover:bg-white';
  const sectionPillClass = theme === 'dark'
    ? 'inline-flex h-7 min-w-7 items-center justify-center rounded-xl bg-slate-900 px-2 text-xs font-semibold text-white'
    : 'inline-flex h-7 min-w-7 items-center justify-center rounded-xl bg-sky-500 px-2 text-xs font-semibold text-white';
  const collapseStorageKey = `side-menu-collapsed:${theme}:${title}`;

  async function handleSwitchRole() {
    await logout();
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
    <Card className={`${containerClass} p-5`}>
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-5">
        <div className="flex items-center gap-3">
          <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl font-semibold ${logoSrc ? 'border border-slate-200 bg-white shadow-none' : logoClass}`}>
            {logoSrc ? (
              <img src={logoSrc} alt={logoAlt} className="h-9 w-9 rounded-lg bg-white p-1 object-contain" />
            ) : (theme === 'dark' ? 'LOGO' : '李')}
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <div className="truncate whitespace-nowrap text-[15px] font-semibold text-slate-900">{title}</div>
              <div className="text-sm text-slate-500">{subtitle}</div>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="mt-1 flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-200 bg-white/90 text-slate-500 hover:bg-slate-50"
          title={collapsed ? '展开导航栏' : '折叠导航栏'}
        >
          <span className={`text-base transition-transform ${collapsed ? 'rotate-180' : ''}`}>◀</span>
        </button>
      </div>
      {!collapsed ? (
        <>
          <div className="mt-5 space-y-4">
            {Object.entries(groupedMenus).map(([section, items]) => (
              <div key={section}>
                <button
                  type="button"
                  onClick={() => toggleSection(section)}
                  className={sectionButtonClass}
                >
                  <span className="flex items-center gap-3">
                    <span className={sectionPillClass}>{section.slice(0, 1)}</span>
                    <span>{section}</span>
                  </span>
                  <span className={`text-slate-400 transition-transform ${resolvedCollapsedSections[section] ? '' : 'rotate-90'}`}>›</span>
                </button>
                {!resolvedCollapsedSections[section] ? (
                  <div className="space-y-2 pl-2">
                    {items.map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        className={({ isActive }) => `block rounded-2xl px-4 py-3 text-sm font-medium transition-all ${isActive ? activeClass : 'text-slate-700 hover:bg-white/80'}`}
                      >
                        {item.label}
                      </NavLink>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          {note ? (
            <div className={`mt-8 rounded-2xl border p-4 ${noteClass}`}>
              <div className="mt-2 text-sm leading-6">{note}</div>
            </div>
          ) : null}
          <button
            type="button"
            onClick={handleSwitchRole}
            className={actionButtonClass}
          >
            {actionLabel}
          </button>
        </>
      ) : null}
    </Card>
  );
}
