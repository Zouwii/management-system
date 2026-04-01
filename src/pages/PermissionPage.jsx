import { useEffect, useState } from 'react';
import { fetchPermissionMatrix } from '../api/dashboard';
import Card from '../components/Card';
import PermissionButton from '../components/PermissionButton';
import SectionTitle from '../components/SectionTitle';
import { BUTTON_PERMISSION_CODES } from '../constants/permissionCodes';
import ManagerLayout from '../layouts/ManagerLayout';
import { permissionMatrix as fallbackMatrix } from '../mock/platformData';

export default function PermissionPage() {
  const [matrix, setMatrix] = useState(fallbackMatrix);

  useEffect(() => {
    let active = true;

    fetchPermissionMatrix().then((response) => {
      if (active) {
        setMatrix(response.data);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return (
    <ManagerLayout>
      <SectionTitle
        title="权限管理"
        desc="建议采用角色权限 + 数据范围权限双层控制，解决员工端、主管端和管理员端的访问边界。"
        right={(
          <div className="flex gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm">RBAC + 数据域控制</div>
            <PermissionButton
              code={BUTTON_PERMISSION_CODES.CONFIGURE_ROLE}
              type="button"
              className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700"
            >
              配置角色
            </PermissionButton>
            <PermissionButton
              code={BUTTON_PERMISSION_CODES.CONFIGURE_DATA_SCOPE}
              type="button"
              className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700"
            >
              配置数据范围
            </PermissionButton>
          </div>
        )}
      />
      <div className="grid grid-cols-3 gap-5">
        <Card className="p-5">
          <div className="text-lg font-semibold">员工</div>
          <div className="mt-3 text-sm leading-7 text-slate-500">登录后仅可见：工时管理、绩效管理、AI分析中心。</div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-emerald-800">可查看本人数据</div>
            <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-rose-800">不可查看组级 / 部门级 / 他人数据</div>
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-lg font-semibold">主管</div>
          <div className="mt-3 text-sm leading-7 text-slate-500">可见：部门总览、组详情、个人详情、绩效页、AI分析页、权限管理页。</div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-emerald-800">可查看本人 + 所管小组 + 所属部门数据</div>
            <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-amber-800">可配置组内页面权限，不可越权看其他部门</div>
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-lg font-semibold">管理员</div>
          <div className="mt-3 text-sm leading-7 text-slate-500">可见全部页面与配置项，负责账号、角色、菜单、数据权限和审计。</div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-emerald-800">可管理全平台角色与范围</div>
            <div className="rounded-2xl border border-sky-100 bg-sky-50 px-4 py-3 text-sky-800">可配置功能开关、组织树和字段脱敏</div>
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
          <div className="text-lg font-semibold">推荐权限模型</div>
          <div className="mt-1 text-sm text-slate-500">前端菜单权限、页面权限、按钮权限、数据权限分层设计。</div>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-white text-slate-500">
              <tr>
                <th className="px-5 py-4 text-left font-medium">权限层</th>
                <th className="px-5 py-4 text-left font-medium">控制内容</th>
                <th className="px-5 py-4 text-left font-medium">员工</th>
                <th className="px-5 py-4 text-left font-medium">主管</th>
                <th className="px-5 py-4 text-left font-medium">管理员</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((row, index) => (
                <tr key={row[0]} className={index !== matrix.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-5 py-4 font-medium text-slate-900">{row[0]}</td>
                  <td className="px-5 py-4 text-slate-600">{row[1]}</td>
                  <td className="px-5 py-4 text-slate-600">{row[2]}</td>
                  <td className="px-5 py-4 text-slate-600">{row[3]}</td>
                  <td className="px-5 py-4 text-slate-600">{row[4]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-5">
        <Card className="p-5">
          <div className="text-lg font-semibold">前端实现建议</div>
          <div className="mt-4 text-sm leading-7 text-slate-600">
            登录成功后返回 role、menuCodes、pageScopes、dataScopes。前端根据 menuCodes 渲染侧边栏，根据 pageScopes 控制路由可访问性，根据 dataScopes 控制请求参数中的数据范围。
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-lg font-semibold">后端实现建议</div>
          <div className="mt-4 text-sm leading-7 text-slate-600">
            后端必须做二次校验，不能只靠前端隐藏菜单。建议按 user_id、team_id、department_id 建立数据权限映射，并对个人绩效、AI建议、敏感评价字段进行服务端裁剪。
          </div>
        </Card>
      </div>
    </ManagerLayout>
  );
}
