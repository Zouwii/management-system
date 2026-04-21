import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { API_MODE, API_MODES } from '../constants/api';
import { useAuthStore } from '../store/authStore';
import { getDefaultHomePath } from '../utils/permission';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((state) => state.login);
  const restoreSession = useAuthStore((state) => state.restoreSession);
  const isLoading = useAuthStore((state) => state.isLoading);
  const [message, setMessage] = useState('');
  const isRealMode = API_MODE === API_MODES.REAL;
  const authError = useMemo(() => new URLSearchParams(location.search).get('auth_error') || '', [location.search]);

  useEffect(() => {
    let active = true;
    async function boot() {
      if (!isRealMode) return;
      if (authError) {
        setMessage(decodeURIComponent(authError));
        return;
      }
      const user = await restoreSession();
      if (!active || !user) return;
      const fallbackPath = getDefaultHomePath(user);
      const nextPath = location.state?.from ?? user.homePath ?? fallbackPath;
      navigate(nextPath, { replace: true });
    }
    boot();
    return () => {
      active = false;
    };
  }, [authError, isRealMode, location.state, navigate, restoreSession]);

  async function handleLogin() {
    try {
      setMessage('');
      const user = await login(isRealMode ? {} : { account: 'admin', password: '123456' });
      if (isRealMode) return;
      const fallbackPath = getDefaultHomePath(user);
      const nextPath = location.state?.from ?? user.homePath ?? fallbackPath;
      navigate(nextPath, { replace: true });
    } catch (error) {
      setMessage(error.message || '登录失败');
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[radial-gradient(circle_at_top,#eef4fb_0%,#f7f9fc_38%,#eef2f7_100%)] px-6 py-10 text-slate-900">
      <div className="relative w-[760px] overflow-hidden rounded-[40px] border border-white/70 bg-white/88 p-16 shadow-[0_30px_100px_rgba(15,23,42,0.12)] backdrop-blur">
        <div className="absolute -top-24 -right-16 h-56 w-56 rounded-full bg-sky-100/70 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-indigo-100/70 blur-3xl" />

        <div className="relative text-center">
          <div className="mt-8 text-[44px] font-bold tracking-[-0.02em] leading-tight text-slate-900">
            本体开发部数据管理平台
          </div>

          <div className="mt-5 text-lg text-slate-600">
            数据驱动 · AI驱动 · 研发效能提升
          </div>

          <div className="mx-auto mt-8 h-px w-24 bg-gradient-to-r from-transparent via-slate-300 to-transparent" />

          <div className="mt-10 text-[18px] font-semibold text-slate-800">
            登录系统
          </div>

          {message ? (
            <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
              {message}
            </div>
          ) : null}

          <button
            type="button"
            disabled={isLoading}
            onClick={handleLogin}
            className="mt-12 h-16 w-full rounded-full bg-gradient-to-r from-slate-900 to-slate-700 text-lg font-semibold text-white shadow-[0_18px_30px_rgba(15,23,42,0.18)] transition hover:translate-y-[-1px] hover:shadow-[0_22px_36px_rgba(15,23,42,0.2)] disabled:cursor-not-allowed disabled:opacity-70"
          >
            使用钉钉登录
          </button>

          <div className="mt-5 text-sm text-slate-400">
            自动识别身份并进入系统
          </div>
        </div>
      </div>
    </div>
  );
}
