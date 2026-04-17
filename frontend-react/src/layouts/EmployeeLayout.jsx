import { useState } from 'react';
import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getMenuRoutesByRole } from '../utils/permission';

export default function EmployeeLayout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.EMPLOYEE;
  const useEmployeeTheme = role === ROLES.EMPLOYEE;
  const menus = getMenuRoutesByRole(sideMenuConfig, user ?? role).map((route) => ({
    label: useEmployeeTheme ? route.employeeLabel ?? route.label : route.label,
    section: useEmployeeTheme ? route.employeeSection ?? route.section : route.section,
    to: route.path,
  }));

  const title = useEmployeeTheme ? user?.name ?? '李四' : '本体开发部数据管理平台';
  const subtitle = useEmployeeTheme
    ? `${user?.team ?? '导航组'} / ${ROLE_LABELS[role]}个人端`
    : `${ROLE_LABELS[role]}端 / 组织级权限`;

  const note = '';

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className={collapsed ? 'col-span-1' : 'col-span-2'}>
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
      <main className={collapsed ? 'col-span-11 space-y-6' : 'col-span-10 space-y-6'}>{children}</main>
    </div>
  );
}
