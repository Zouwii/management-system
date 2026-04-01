import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { registerUser } from '../api/auth';
import Card from '../components/Card';
import { useAuthStore } from '../store/authStore';
import { getDefaultHomePath } from '../utils/permission';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((state) => state.login);
  const isLoading = useAuthStore((state) => state.isLoading);
  const [form, setForm] = useState({ account: '', password: '' });
  const [message, setMessage] = useState('');

  async function handleLogin() {
    try {
      setMessage('');
      const user = await login(form);
      const fallbackPath = getDefaultHomePath(user.role);
      const nextPath = location.state?.from ?? user.homePath ?? fallbackPath;
      navigate(nextPath, { replace: true });
    } catch (error) {
      setMessage(error.message || '登录失败');
    }
  }

  async function handleRegister() {
    await registerUser(form);
    setMessage('当前为 mock 环境，注册入口已预留，默认请使用 README 中的演示账号登录。');
  }

  function handleChange(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    await handleLogin();
  }

  async function handleRegisterClick(event) {
    event.preventDefault();
    await handleRegister();
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="grid min-h-[calc(100vh-3rem)] grid-cols-2 gap-6">
        <Card className="flex flex-col justify-between overflow-hidden bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(240,249,255,0.92))] p-8">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.16em] text-sky-600">本体开发部数据平台</div>
            <div className="mt-4 text-4xl font-semibold text-slate-900">登录页</div>
            <div className="mt-4 text-sm leading-7 text-slate-500">
              建议采用角色权限 + 数据范围权限双层控制，解决员工端、主管端和管理员端的访问边界。
            </div>
          </div>
          <div className="rounded-3xl border border-sky-100 bg-[linear-gradient(135deg,rgba(224,242,254,0.75),rgba(236,253,245,0.9))] p-5">
            <div className="text-sm font-medium text-slate-900">权限提示</div>
            <div className="mt-2 text-sm leading-6 text-slate-500">
              登录成功后返回 role、menuCodes、pageScopes、dataScopes。前端根据 menuCodes 渲染侧边栏，根据 pageScopes 控制路由可访问性，根据 dataScopes 控制请求参数中的数据范围。
            </div>
          </div>
        </Card>
        <Card className="bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,250,252,0.94))] p-8">
          <div className="text-lg font-semibold text-slate-900">账号登录</div>
          <div className="mt-1 text-sm text-slate-500">请输入账号和密码登录，注册入口已预留。</div>
          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <div className="mb-2 text-sm text-slate-500">账号</div>
              <input
                value={form.account}
                onChange={(event) => handleChange('account', event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 shadow-inner"
                placeholder="请输入账号"
              />
            </div>
            <div>
              <div className="mb-2 text-sm text-slate-500">密码</div>
              <input
                type="password"
                value={form.password}
                onChange={(event) => handleChange('password', event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 text-sm text-slate-700 outline-none placeholder:text-slate-400 shadow-inner"
                placeholder="请输入密码"
              />
            </div>
            {message ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                {message}
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <button
                type="submit"
                disabled={isLoading}
                className="rounded-2xl bg-gradient-to-r from-slate-900 to-sky-700 px-4 py-3 text-center font-medium text-white shadow-[0_18px_30px_-18px_rgba(2,132,199,0.85)]"
              >
                登录
              </button>
              <button
                type="button"
                onClick={handleRegisterClick}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center font-medium text-slate-700"
              >
                注册
              </button>
            </div>
          </form>
          <div className="mt-8 grid grid-cols-3 gap-4 text-sm">
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-emerald-800">可查看本人数据</div>
            <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-amber-800">可查看本人 + 所管小组 + 所属部门数据</div>
            <div className="rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sky-800">可管理全平台角色与范围</div>
          </div>
        </Card>
      </div>
    </div>
  );
}
