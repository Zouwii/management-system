import { request } from '../../request';
import { mockAccounts, mockUsers } from '../../../mock/auth';

export function mockLoginByCredentials({ account, password }) {
  return request(() => {
    const accountRecord = Object.values(mockAccounts).find(
      (item) => item.account === account && item.password === password,
    );

    if (!accountRecord) {
      throw new Error('账号或密码错误');
    }

    return mockUsers[accountRecord.role];
  });
}

export function mockRegister() {
  return request(() => ({ success: true }));
}
