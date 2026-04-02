import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { loginByCredentials } from '../api/auth';
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
          const response = await loginByCredentials(credentials);
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
      logout() {
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
