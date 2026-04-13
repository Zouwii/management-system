import { API_BASE_URL, API_MODE, API_MODES } from '../constants/api';
import { useSessionExpiredStore } from '../store/sessionExpiredStore';

const DEFAULT_HEADERS = {
  'Content-Type': 'application/json',
};

function buildUrl(path) {
  if (path.startsWith('http')) {
    return path;
  }

  return `${API_BASE_URL}${path}`;
}

export async function httpRequest(path, options = {}) {
  const { skipSessionExpired = false, ...fetchOptions } = options;
  const response = await fetch(buildUrl(path), {
    credentials: 'include',
    headers: DEFAULT_HEADERS,
    ...fetchOptions,
  });

  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }

  if (response.status === 401 && !skipSessionExpired) {
    useSessionExpiredStore.getState().show();
    throw new Error(data?.error || 'unauthenticated');
  }

  if (!response.ok) {
    throw new Error(data?.error || `请求失败: ${response.status}`);
  }

  return data;
}

export function createApiSwitch(mockHandler, realHandler) {
  return async (...args) => {
    if (API_MODE === API_MODES.REAL) {
      return realHandler(...args);
    }

    return mockHandler(...args);
  };
}
