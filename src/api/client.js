import { API_BASE_URL, API_MODE, API_MODES } from '../constants/api';

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
  const response = await fetch(buildUrl(path), {
    headers: DEFAULT_HEADERS,
    ...options,
  });

  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }

  return response.json();
}

export function createApiSwitch(mockHandler, realHandler) {
  return async (...args) => {
    if (API_MODE === API_MODES.REAL) {
      return realHandler(...args);
    }

    return mockHandler(...args);
  };
}
