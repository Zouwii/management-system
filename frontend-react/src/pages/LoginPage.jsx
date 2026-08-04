import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { API_MODE, API_MODES } from '../constants/api';
import { useAuthStore } from '../store/authStore';
import { fetchLocalUsers, offlineLogin } from '../api/auth';
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

  // 离线登录状态
  const [showOffline, setShowOffline] = useState(false);
  const [localUsers, setLocalUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    if (showOffline) {
      fetchLocalUsers()
        .then((res) => setLocalUsers(res?.data?.users || []))
        .catch(() => setLocalUsers([]));
    }
  }, [showOffline]);

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

      if (showOffline) {
        // 离线登录：直接调 API，不走 authStore 封装
        const res = await offlineLogin({ user_id: selectedUserId, password });
        const user = res.data;
        if (!user || !user.role) {
          setMessage('登录返回数据异常: ' + JSON.stringify(res));
          return;
        }
        // 直接设置 authStore
        useAuthStore.setState({ user, isAuthenticated: true, isLoading: false });
        const fallbackPath = getDefaultHomePath(user);
        const nextPath = location.state?.from ?? user.homePath ?? fallbackPath;
        navigate(nextPath, { replace: true });
        return;
      }

      // 钉钉登录
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
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,#eef4fb_0%,#f7f9fc_38%,#eef2f7_100%)] px-3 py-6 text-slate-900 sm:px-6 sm:py-10">
      <div className="relative w-full max-w-[760px] overflow-hidden rounded-[28px] border border-white/70 bg-white/88 p-6 shadow-[0_30px_100px_rgba(15,23,42,0.12)] backdrop-blur sm:rounded-[36px] sm:p-10 lg:p-16">
        <div className="absolute -top-24 -right-16 h-56 w-56 rounded-full bg-sky-100/70 blur-3xl" />
        <div className="absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-indigo-100/70 blur-3xl" />

        <div className="relative text-center">
          <div className="mt-5 text-3xl font-bold leading-tight tracking-[-0.02em] text-slate-900 sm:mt-8 sm:text-[38px] lg:text-[44px]">
            本体开发部数据管理平台
          </div>

          <div className="mt-4 text-base text-slate-600 sm:mt-5 sm:text-lg">
            数据驱动 · AI驱动 · 研发效能提升
          </div>

          <div className="mx-auto mt-8 h-px w-24 bg-gradient-to-r from-transparent via-slate-300 to-transparent" />

          <div className="mt-10 text-[18px] font-semibold text-slate-800">
            {showOffline ? '离线模式登录' : '登录系统'}
          </div>

          {showOffline && (
            <div className="mt-3 text-sm text-amber-600 bg-amber-50 rounded-xl px-4 py-2">
              ⚠️ 离线模式：使用本地账户登录，已断开钉钉 API 连接
            </div>
          )}

          {message ? (
            <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
              {message}
            </div>
          ) : null}

          {showOffline ? (
            <div className="mt-8 space-y-4">
              <div className="text-left">
                <label className="block text-sm font-medium text-slate-700 mb-1">选择用户</label>
                <select
                  value={selectedUserId}
                  onChange={(e) => {
                    setSelectedUserId(e.target.value);
                  }}
                  className="w-full h-12 rounded-2xl border border-slate-300 bg-white px-4 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400"
                >
                  <option value="">-- 请选择 --</option>
                  {localUsers.map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="text-left">
                <label className="block text-sm font-medium text-slate-700 mb-1">密码</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                  className="w-full h-12 rounded-2xl border border-slate-300 bg-white px-4 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleLogin();
                  }}
                />
              </div>
            </div>
          ) : null}

          <button
            type="button"
            disabled={
              isLoading ||
              (showOffline && (!selectedUserId || !password))
            }
            onClick={handleLogin}
            className="mt-8 h-14 w-full rounded-full bg-gradient-to-r from-slate-900 to-slate-700 text-base font-semibold text-white shadow-[0_18px_30px_rgba(15,23,42,0.18)] transition hover:translate-y-[-1px] hover:shadow-[0_22px_36px_rgba(15,23,42,0.2)] disabled:cursor-not-allowed disabled:opacity-70 sm:mt-12 sm:h-16 sm:text-lg"
          >
            {showOffline ? '本地登录' : '使用钉钉登录'}
          </button>

          {/* 底部切换链接 */}
          <div className="mt-6 text-sm">
            <button
              type="button"
              onClick={() => {
                setShowOffline(!showOffline);
                setMessage('');
              }}
              className="text-slate-400 hover:text-indigo-500 transition"
            >
              {showOffline ? '← 返回钉钉登录' : '离线模式登录'}
            </button>
          </div>

          <div className="mt-2 text-sm text-slate-400">
            {showOffline ? '选择用户并输入密码进入系统' : '自动识别身份并进入系统'}
          </div>
        </div>
      </div>
    </div>
  );
}
