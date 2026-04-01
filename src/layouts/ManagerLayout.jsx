import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getDataScopeLabel } from '../utils/dataScope';
import { getMenuRoutesByRole } from '../utils/permission';

export default function ManagerLayout({ children }) {
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.MANAGER;
  const menus = getMenuRoutesByRole(sideMenuConfig, role).map((route) => ({
    label: route.label,
    section: route.section,
    to: route.path,
  }));

  const subtitle = role === ROLES.ADMIN
    ? `${ROLE_LABELS[role]} / 全局权限`
    : `${ROLE_LABELS[role]}端 / 组织级权限`;

  const note = role === ROLES.ADMIN
    ? `管理员可访问全部页面与全部数据，当前数据范围：${getDataScopeLabel(user?.dataScope)}。`
    : `主管端可查看个人、组级、部门级数据，并配置页面权限、角色权限和数据范围。当前数据范围：${getDataScopeLabel(user?.dataScope)}。`;

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className="col-span-3">
        <SideMenu
          title="本体开发部数据平台"
          subtitle={subtitle}
          menus={menus}
          theme="dark"
          note={note}
          actionTo={ROUTE_PATHS.LOGIN}
        />
      </aside>
      <main className="col-span-9 space-y-6">{children}</main>
    </div>
  );
}
