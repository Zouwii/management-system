import { useState } from 'react';
import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getMenuRoutesByRole, hasRoleAccess } from '../utils/permission';

export default function EmployeeLayout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.EMPLOYEE;
  const useEmployeeTheme = role === ROLES.EMPLOYEE;
  const menus = getMenuRoutesByRole(sideMenuConfig, user ?? role).map((route) => ({
    label: useEmployeeTheme ? route.employeeLabel ?? route.label : route.label,
    section: useEmployeeTheme ? route.employeeSection ?? route.section : route.section,
    to: route.path,
    children: (route.children || [])
      .filter((child) => hasRoleAccess(role, child.allowedRoles))
      .map((child) => ({
        label: useEmployeeTheme ? child.employeeLabel ?? child.label : child.label,
        to: child.path,
      })),
  }));

  const title = useEmployeeTheme ? user?.name ?? '李四' : '本体开发部数据管理平台';
  const subtitle = useEmployeeTheme
    ? `${user?.team ?? '导航组'} / ${ROLE_LABELS[role]}个人端`
    : `${ROLE_LABELS[role]}端 / 组织级权限`;

  const note = '';

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-6">
      <aside className={`min-w-0 ${collapsed ? 'lg:col-span-1' : 'lg:col-span-2'}`}>
        <SideMenu
          title={title}
          subtitle={subtitle}
          menus={menus}
          theme={useEmployeeTheme ? 'blue' : 'dark'}
          logoSrc="/竖版-中文(1).png"
          logoAlt="迦智科技"
          note={note}
          actionLabel="退出登录"
          actionTo={ROUTE_PATHS.LOGIN}
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((prev) => !prev)}
        />
      </aside>
      <main className={`min-w-0 space-y-4 lg:space-y-6 ${collapsed ? 'lg:col-span-11' : 'lg:col-span-10'}`}>{children}</main>
    </div>
  );
}
