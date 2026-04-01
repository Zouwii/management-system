import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getDataScopeLabel } from '../utils/dataScope';
import { getMenuRoutesByRole } from '../utils/permission';

export default function EmployeeLayout({ children }) {
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.EMPLOYEE;
  const useEmployeeTheme = role === ROLES.EMPLOYEE;
  const menus = getMenuRoutesByRole(sideMenuConfig, role).map((route) => ({
    label: useEmployeeTheme ? route.employeeLabel ?? route.label : route.label,
    section: useEmployeeTheme ? route.employeeSection ?? route.section : route.section,
    to: route.path,
  }));

  const title = useEmployeeTheme ? user?.name ?? '李四' : '本体开发部数据平台';
  const subtitle = useEmployeeTheme
    ? `${user?.team ?? '导航组'} / ${ROLE_LABELS[role]}个人端`
    : `${ROLE_LABELS[role]}端 / 组织级权限`;

  const note = useEmployeeTheme
    ? `员工端仅允许查看本人数据，不可访问组级和部门级页面。当前数据范围：${getDataScopeLabel(user?.dataScope)}。`
    : `${ROLE_LABELS[role]}可查看个人、组级、部门级数据。当前数据范围：${getDataScopeLabel(user?.dataScope)}。`;

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className="col-span-3">
        <SideMenu
          title={title}
          subtitle={subtitle}
          menus={menus}
          theme={useEmployeeTheme ? 'blue' : 'dark'}
          note={note}
          actionTo={ROUTE_PATHS.LOGIN}
        />
      </aside>
      <main className="col-span-9 space-y-6">{children}</main>
    </div>
  );
}
