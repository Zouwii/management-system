import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import Card from './Card';
import KnowledgeChatDialog from './KnowledgeChatDialog';
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
    ? 'border-slate-200/80 bg-white/88 lg:sticky lg:top-6'
    : 'border-sky-100/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(240,249,255,0.92))] lg:sticky lg:top-6';
  const actionButtonClass = theme === 'dark'
    ? 'mt-4 block rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center text-sm font-medium text-slate-700 hover:bg-slate-50'
    : 'mt-4 block rounded-2xl border border-sky-100 bg-white/90 px-4 py-3 text-center text-sm font-medium text-sky-700 shadow-[0_10px_24px_-20px_rgba(14,165,233,0.9)] hover:bg-sky-50';
  const sectionButtonClass = theme === 'dark'
    ? 'mb-3 flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm font-semibold text-slate-900 shadow-[0_8px_20px_-18px_rgba(15,23,42,0.35)] hover:bg-white'
    : 'mb-3 flex w-full items-center justify-between rounded-2xl border border-sky-100 bg-[linear-gradient(135deg,rgba(239,246,255,0.95),rgba(236,253,245,0.9))] px-4 py-3 text-left text-sm font-semibold text-sky-950 shadow-[0_12px_24px_-18px_rgba(14,165,233,0.35)] hover:bg-white';
  const sectionPillClass = theme === 'dark'
    ? 'inline-flex h-7 min-w-7 items-center justify-center rounded-xl bg-slate-900 px-2 text-xs font-semibold text-white'
    : 'inline-flex h-7 min-w-7 items-center justify-center rounded-xl bg-sky-500 px-2 text-xs font-semibold text-white';
  const chatButtonClass = theme === 'dark'
    ? 'fixed bottom-5 right-5 z-40 flex h-10 w-10 items-center justify-center rounded-full bg-purple-600 text-white shadow-[0_14px_28px_-16px_rgba(88,28,135,0.8)] transition duration-200 hover:bg-purple-700 hover:shadow-[0_18px_36px_-16px_rgba(88,28,135,0.9)] lg:bottom-24 lg:left-0 lg:right-auto lg:-translate-x-1/2 lg:hover:translate-x-0 lg:focus-visible:translate-x-0'
    : 'fixed bottom-5 right-5 z-40 flex h-10 w-10 items-center justify-center rounded-full bg-purple-600 text-white shadow-[0_14px_28px_-16px_rgba(88,28,135,0.8)] transition duration-200 hover:bg-purple-700 hover:shadow-[0_18px_36px_-16px_rgba(88,28,135,0.9)] lg:bottom-24 lg:left-0 lg:right-auto lg:-translate-x-1/2 lg:hover:translate-x-0 lg:focus-visible:translate-x-0';
  const collapseStorageKey = `side-menu-collapsed:${theme}:${title}`;
  const [chatOpen, setChatOpen] = useState(false);

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
      const hasActiveItem = items.some((item) =>
        item.to === location.pathname
        || (item.children || []).some((child) => child.to === location.pathname)
      );
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
    <>
      <Card className={`${containerClass} p-4 lg:p-5`}>
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-5">
          <div className="flex items-center gap-3">
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl font-semibold ${logoSrc ? 'border border-slate-200 bg-white shadow-none' : logoClass}`}>
              {logoSrc ? (
                <img src={logoSrc} alt={logoAlt} className="h-9 w-9 rounded-lg bg-white p-1 object-contain" />
              ) : (theme === 'dark' ? 'LOGO' : '李')}
            </div>
            {!collapsed ? (
              <div className="min-w-0">
                <div className="text-[15px] font-semibold leading-5 text-slate-900 whitespace-nowrap max-[1400px]:whitespace-normal">
                  {title}
                </div>
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
                        <div key={item.to || item.path}>
                          <NavLink
                            to={item.to || item.path}
                            className={({ isActive }) => `block rounded-2xl px-4 py-3 text-sm font-medium transition-all ${isActive ? activeClass : 'text-slate-700 hover:bg-white/80'}`}
                          >
                            {item.label}
                          </NavLink>
                          {item.children?.length > 0 && (
                            <div className="ml-4 mt-1 space-y-1 border-l-2 border-slate-200 pl-3">
                              {item.children.map((child) => (
                                <NavLink
                                  key={child.to}
                                  to={child.to}
                                  className={({ isActive }) => `block rounded-xl px-3 py-2 text-xs font-medium transition-all ${isActive ? activeClass : 'text-slate-500 hover:bg-white/80'}`}
                                >
                                  {child.label}
                                </NavLink>
                              ))}
                            </div>
                          )}
                        </div>
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
      <button
        type="button"
        onClick={() => setChatOpen(true)}
        className={chatButtonClass}
        title="AI知识库问答"
        aria-label="AI知识库问答"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </button>
      <KnowledgeChatDialog open={chatOpen} onClose={() => setChatOpen(false)} />
    </>
  );
}
