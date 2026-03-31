/**
 * 开发：`npm run dev` 时 Vite 把 /api 代理到 5001，用空串即可同源请求。
 * 生产：构建产物由 Flask 托管，与接口同源，仍用空串。
 */
export const API_BASE = "";

/** 与后端 DEFAULT_WORKHOUR_FIELD_ID 一致：钉钉任务详情里「工时」自定义字段 id */
export const WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8";

/**
 * 工时系数：用于把「有效工作日天数」换算为「预计工时」。
 * 例如 0.7 表示按 70% 的工作强度折算。
 */
export const WORKHOUR_COEFFICIENT = 0.7;
