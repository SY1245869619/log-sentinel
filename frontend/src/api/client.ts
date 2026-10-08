import { message } from 'antd';
import axios, { AxiosError, AxiosResponse } from 'axios';

/**
 * Axios 实例：统一注入 JWT、统一解包 {code,msg,data}、统一错误提示。
 */
const client = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response: AxiosResponse) => {
    const body = response.data;
    if (body && typeof body.code === 'number' && body.code !== 0) {
      // 兜底：即便后端用 200 包装 401，也统一登出
      if (body.code === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        if (!window.location.pathname.startsWith('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(new Error(body.msg));
      }
      message.error(body.msg || '操作失败');
      return Promise.reject(new Error(body.msg));
    }
    return body?.data !== undefined ? body.data : body;
  },
  (error: AxiosError<any>) => {
    const status = error.response?.status;
    const msg = error.response?.data?.msg || error.message || '网络异常';
    if (status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    } else {
      message.error(msg);
    }
    return Promise.reject(error);
  },
);

export default client;
