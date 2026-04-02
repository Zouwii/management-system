import { createApiSwitch } from './client';
import { mockLoginByCredentials, mockRegister } from './providers/mock/auth';
import { realLoginByCredentials, realRegister } from './providers/real/auth';

export const loginByCredentials = createApiSwitch(mockLoginByCredentials, realLoginByCredentials);
export const registerUser = createApiSwitch(mockRegister, realRegister);
