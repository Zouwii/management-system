import { httpRequest } from '../../client';

export function realLoginByCredentials(payload) {
  return httpRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realRegister(payload) {
  return httpRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
