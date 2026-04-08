import { httpRequest } from '../../client';

export function realLoginByCredentials() {
  return httpRequest('/bt/auth/dingtalk/url', {
    method: 'GET',
  });
}

export function realRegister(payload) {
  return httpRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realFetchCurrentUser() {
  return httpRequest('/bt/auth/me', {
    method: 'GET',
  });
}

export function realLogout() {
  return httpRequest('/bt/auth/logout', {
    method: 'POST',
  });
}
