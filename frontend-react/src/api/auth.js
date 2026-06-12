import { createApiSwitch } from './client';
import {
  mockFetchCurrentUser,
  mockLoginByCredentials,
  mockLogout,
  mockRegister,
} from './providers/mock/auth';
import {
  realFetchCurrentUser,
  realFetchLocalUsers,
  realLoginByCredentials,
  realLogout,
  realOfflineLogin,
  realRegister,
} from './providers/real/auth';

export const loginByCredentials = createApiSwitch(mockLoginByCredentials, realLoginByCredentials);
export const registerUser = createApiSwitch(mockRegister, realRegister);
export const fetchCurrentUser = createApiSwitch(mockFetchCurrentUser, realFetchCurrentUser);
export const logoutCurrentUser = createApiSwitch(mockLogout, realLogout);

// 离线模式专用：获取用户列表 + 本地登录（仅 real 模式，无 mock）
export const fetchLocalUsers = realFetchLocalUsers;
export const offlineLogin = realOfflineLogin;
