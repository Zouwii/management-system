export const API_MODES = {
  MOCK: 'mock',
  REAL: 'real',
};

export const API_MODE = import.meta.env.VITE_API_MODE || API_MODES.REAL;
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
