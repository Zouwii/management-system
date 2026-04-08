import { createApiSwitch } from './client';
import {
  mockFetchCurrentUser,
  mockLoginByCredentials,
  mockLogout,
  mockRegister,
} from './providers/mock/auth';
import {
  realFetchCurrentUser,
  realLoginByCredentials,
  realLogout,
  realRegister,
} from './providers/real/auth';

export const loginByCredentials = createApiSwitch(mockLoginByCredentials, realLoginByCredentials);
export const registerUser = createApiSwitch(mockRegister, realRegister);
export const fetchCurrentUser = createApiSwitch(mockFetchCurrentUser, realFetchCurrentUser);
export const logoutCurrentUser = createApiSwitch(mockLogout, realLogout);
