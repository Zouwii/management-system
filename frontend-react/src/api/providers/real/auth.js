import { httpRequest } from '../../client';

export function realLoginByCredentials() {
  return httpRequest('/bt/auth/dingtalk/url', {
    method: 'GET',
    skipSessionExpired: true,
  });
}

export function realRegister(payload) {
  return httpRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
    skipSessionExpired: true,
  });
}

export function realFetchCurrentUser() {
  return httpRequest('/bt/auth/me', {
    method: 'GET',
    skipSessionExpired: true,
  });
}

export function realLogout() {
  return httpRequest('/bt/auth/logout', {
    method: 'POST',
    skipSessionExpired: true,
  });
}

// 离线模式：获取本地用户列表
export function realFetchLocalUsers() {
  return httpRequest('/bt/auth/local/users', {
    method: 'GET',
    skipSessionExpired: true,
  });
}

// 离线模式：本地登录
export function realOfflineLogin(payload) {
  return httpRequest('/bt/auth/local/login', {
    method: 'POST',
    body: JSON.stringify(payload),
    skipSessionExpired: true,
  });
}
