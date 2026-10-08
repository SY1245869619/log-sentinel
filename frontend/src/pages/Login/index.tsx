import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Form, Input, Typography } from 'antd';
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../../api/client';
import { resolveWallpaper, WALLPAPERS } from '../../utils/wallpaper';

interface LoginForm {
  username: string;
  password: string;
}

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [wallpaper, setWallpaper] = useState(WALLPAPERS.glass.bg);

  // 壁纸由系统设置统一配置（登录页无需鉴权读取）
  useEffect(() => {
    client
      .get('/system/login-config')
      .then((res: any) => setWallpaper(resolveWallpaper(res?.wallpaper || 'ocean')))
      .catch(() => {});
  }, []);

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      const data: any = await client.post('/auth/login', values);
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      // 登录成功默认进入仪表盘（不再强制修改密码，入口在右上角用户菜单）
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: wallpaper,
        transition: 'background 0.5s ease',
        position: 'relative',
      }}
    >
      <div className="login-glass-card" style={{ width: 400, padding: '40px 36px' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div
            style={{
              width: 56, height: 56, margin: '0 auto 16px',
              borderRadius: 14, background: '#1677ff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 28, color: '#fff',
            }}
          >
            ⚡
          </div>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            日志监控告警系统
          </Typography.Title>
          <Typography.Text type="secondary">
            LogSentinel · 日志监控与钉钉告警平台
          </Typography.Text>
        </div>
        <Form<LoginForm> onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginTop: 8 }}>
            <Button type="primary" htmlType="submit" block loading={loading}>
              登 录
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  );
};

export default LoginPage;
