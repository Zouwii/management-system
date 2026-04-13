import { useNavigate } from 'react-router-dom';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { useSessionExpiredStore } from '../store/sessionExpiredStore';

export default function SessionExpiredModal() {
  const open = useSessionExpiredStore((s) => s.open);
  const hide = useSessionExpiredStore((s) => s.hide);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  if (!open) return null;

  async function handleRelogin() {
    hide();
    await logout();
    navigate(ROUTE_PATHS.LOGIN, { replace: true });
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-expired-title"
        className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        <h2 id="session-expired-title" className="text-lg font-semibold text-slate-900">
          登录已过期
        </h2>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          当前登录状态已失效，请重新登录后继续使用。
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={handleRelogin}
            className="rounded-2xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
          >
            重新登录
          </button>
        </div>
      </div>
    </div>
  );
}
