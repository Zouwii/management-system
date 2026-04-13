import { create } from 'zustand';

/**
 * 登录态失效（401）时全局弹窗，避免多请求重复弹出。
 */
export const useSessionExpiredStore = create((set, get) => ({
  open: false,
  show: () => {
    if (get().open) return;
    set({ open: true });
  },
  hide: () => set({ open: false }),
}));
