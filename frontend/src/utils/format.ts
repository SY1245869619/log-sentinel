import dayjs from 'dayjs';

/** 后端时间（ISO 字符串）→ 页面展示格式 */
export function fmt(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

/** 状态 → Tag 颜色（语义色，契合主题 token） */
export const STATUS_COLOR: Record<string, string> = {
  RUNNING: 'success',
  ONLINE: 'success',
  SUCCESS: 'success',
  NOTIFIED: 'success',
  STOPPED: 'default',
  UNKNOWN: 'default',
  RECORD_ONLY: 'default',
  ERROR: 'error',
  FAILED: 'error',
  SUPPRESSED: 'warning',
  RECONNECTING: 'warning',
  AGGREGATED: 'processing',
  RESEND_SUCCESS: 'success',
  RESEND_FAILED: 'error',
  CRITICAL: 'error',
  MAJOR: 'warning',
  MINOR: 'default',
};

export const STATUS_TEXT: Record<string, string> = {
  RUNNING: '运行中', STOPPED: '停止', ERROR: '异常', RECONNECTING: '重连中',
  ONLINE: '在线', OFFLINE: '离线', FAILED: '失败', UNKNOWN: '未知', LOCAL: '本机',
  NOTIFIED: '已通知', SUPPRESSED: '已抑制', AGGREGATED: '已聚合', RECORD_ONLY: '仅记录',
  SUCCESS: '成功', RESEND_SUCCESS: '重发成功', RESEND_FAILED: '重发失败',
  CRITICAL: '严重', MAJOR: '重要', MINOR: '次要',
};

export function statusText(v?: string | null): string {
  return (v && STATUS_TEXT[v]) || v || '-';
}
