import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { fetchCurrentUser, loginByCredentials, logoutCurrentUser } from '../api/auth';
import { API_MODE, API_MODES } from '../constants/api';
import { hasPermissionCode } from '../utils/permission';

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      async login(credentials) {
        set({ isLoading: true });

        try {
          if (API_MODE === API_MODES.REAL) {
            const loginUrlResponse = await loginByCredentials(credentials);
            const loginUrl = loginUrlResponse?.data?.url;
            const corpId = loginUrlResponse?.data?.corpId;
            const clientId = loginUrlResponse?.data?.clientId;
            if (!loginUrl) {
              throw new Error('未获取到钉钉登录地址');
            }
            console.log('[auth][dingtalk] login bootstrap', {
              corpId,
              clientId,
              url: loginUrl,
            });
            window.location.href = loginUrl;
            return null;
          }

          const response = await loginByCredentials(credentials || {});
          set({
            user: response.data,
            isAuthenticated: true,
            isLoading: false,
          });
          return response.data;
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },
      async restoreSession() {
        if (API_MODE !== API_MODES.REAL) return null;
        set({ isLoading: true });
        try {
          const response = await fetchCurrentUser();
          set({
            user: response.data,
            isAuthenticated: true,
            isLoading: false,
          });
          return response.data;
        } catch {
          set({
            user: null,
            isAuthenticated: false,
            isLoading: false,
          });
          return null;
        }
      },
      async logout() {
        if (API_MODE === API_MODES.REAL) {
          try {
            await logoutCurrentUser();
          } catch {
            // 无论后端是否成功，前端都必须清理本地状态
          }
        }
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      },
      hasPermission(code) {
        return hasPermissionCode(get().user, code);
      },
    }),
    {
      name: 'body-dev-auth',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
