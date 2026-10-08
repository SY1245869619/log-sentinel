import {
  AlertOutlined, DashboardOutlined, FileSearchOutlined, KeyOutlined,
  LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined, NotificationOutlined,
  SafetyOutlined, SettingOutlined, UserOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Dropdown, Layout, Menu, notification } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { getToken, getUser, hasRole, logout } from '../store/auth';
import { loadAndApplyWallpaper } from '../utils/wallpaper';

const { Sider, Content, Header } = Layout;

interface MenuItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
  roles?: string[];
  children?: MenuItem[];
}

const MENU: MenuItem[] = [
  { key: '/dashboard', label: '仪表盘', icon: <DashboardOutlined /> },
  {
    key: 'monitor', label: '监控中心', icon: <AlertOutlined />, children: [
      { key: '/error-logs', label: '报错日志' },
      { key: '/alerts', label: '告警记录' },
      { key: '/collector', label: '采集管理' },
    ],
  },
  {
    // 按配置先后排序：主机 → 项目 → 日志源 → 关键字/错误码/@人 → 渠道/模板 → 告警规则
    key: 'config', label: '配置中心', icon: <SettingOutlined />, children: [
      { key: '/hosts', label: '主机管理' },
      { key: '/agents', label: 'Agent管理' },
      { key: '/projects', label: '项目管理' },
      { key: '/log-sources', label: '日志源管理' },
      { key: '/keywords', label: '关键字配置' },
      { key: '/error-codes', label: '错误码配置' },
      { key: '/mentions', label: '@人配置' },
      { key: '/channels', label: '通知渠道' },
      { key: '/templates', label: '通知模板' },
      { key: '/alert-rules', label: '告警规则' },
    ],
  },
  {
    key: 'records', label: '记录中心', icon: <FileSearchOutlined />, children: [
      { key: '/notify-records', label: '通知记录' },
      { key: '/notify-fail-records', label: '通知失败' },
      { key: '/audit-logs', label: '操作审计' },
    ],
  },
  {
    key: 'system', label: '系统管理', icon: <SafetyOutlined />, children: [
      { key: '/users', label: '用户管理', roles: ['ADMIN'] },
      { key: '/roles', label: '角色管理', roles: ['ADMIN'] },
      { key: '/settings', label: '系统设置', roles: ['ADMIN'] },
    ],
  },
];

function filterMenu(items: MenuItem[]): MenuItem[] {
  return items
    .filter((i) => !i.roles || hasRole(...i.roles))
    .map((i) => (i.children ? { ...i, children: filterMenu(i.children) } : i))
    .filter((i) => !i.children || i.children.length > 0);
}

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getUser();
  const [api, contextHolder] = notification.useNotification();
  const [collapsed, setCollapsed] = useState(false);
  const menuItems = useMemo(() => filterMenu(MENU), []);

  // 全局壁纸：进入系统即应用（所有页面生效）
  useEffect(() => {
    loadAndApplyWallpaper();
  }, []);

  // SSE 实时推送：新告警 / 通知结果 / 采集异常
  useEffect(() => {
    const source = new EventSource(`/api/v1/stream?token=${getToken()}`);
    source.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.type === 'alert') {
          api.warning({
            title: '新告警',
            description: `项目 ${event.project} 产生 ${event.severity} 级别告警`,
            placement: 'bottomRight',
          });
        } else if (event.type === 'notify' && event.status === 'FAILED') {
          api.error({
            title: '通知发送失败',
            description: `渠道 ${event.channel}：${event.title}`,
            placement: 'bottomRight',
          });
        } else if (event.type === 'collector') {
          api.error({
            title: '采集异常',
            description: `日志源 #${event.source_id} ${event.status}：${event.error || ''}`,
            placement: 'bottomRight',
          });
        }
      } catch {
        // 忽略心跳等非 JSON 消息
      }
    };
    return () => source.close();
  }, [api]);

  const selectedKey = useMemo(() => {
    const keys = MENU.flatMap((m) => [m.key, ...(m.children || []).map((c) => c.key)]);
    return keys.filter((k) => location.pathname.startsWith(k)).sort((a, b) => b.length - a.length)[0];
  }, [location.pathname]);

  return (
    <Layout style={{ minHeight: '100vh' }} className="app-layout">
      {contextHolder}
      <Sider
        width={220}
        collapsed={collapsed}
        trigger={null}
        collapsedWidth={72}
        style={{
          position: 'sticky', top: 0, height: '100vh',
          display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <NotificationOutlined style={{ fontSize: 20, color: '#1677ff' }} />
          {!collapsed && (
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, lineHeight: 1.3 }}>
                日志监控告警系统
              </div>
              <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>LogSentinel</div>
            </div>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          <Menu
            mode="inline"
            className="app-menu"
            style={{ background: 'transparent', border: 'none' }}
            selectedKeys={selectedKey ? [selectedKey] : []}
            defaultOpenKeys={collapsed ? [] : ['monitor', 'config', 'records', 'system']}
            items={menuItems as any}
            onClick={({ key }) => navigate(key)}
          />
        </div>
      </Sider>
      <Layout className="app-layout">
        {/* 紧凑顶栏：左侧收缩按钮 + 右上角用户入口 */}
        <Header
          style={{
            height: 48, lineHeight: '48px', padding: '0 20px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: 'transparent', position: 'sticky', top: 0, zIndex: 10,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{ fontSize: 16 }}
          />
          <Dropdown
            menu={{
              items: [
                { key: 'pwd', icon: <KeyOutlined />, label: '修改密码' },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
              ],
              onClick: ({ key }) => {
                if (key === 'pwd') navigate('/change-password');
                if (key === 'logout') logout();
              },
            }}
          >
            <span style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Avatar size={28} icon={<UserOutlined />} />
            </span>
          </Dropdown>
        </Header>
        <Content style={{ padding: '0 24px 24px', overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
