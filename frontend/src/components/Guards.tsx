import { Button, Result } from 'antd';
import React from 'react';
import { Navigate } from 'react-router-dom';
import { hasRole, isLoggedIn } from '../store/auth';

/** 登录守卫 */
export const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

/** 角色守卫 */
export const RequireRole: React.FC<{ roles: string[]; children: React.ReactNode }> = ({
  roles,
  children,
}) => {
  if (!hasRole(...roles)) {
    return (
      <Result
        status="403"
        title="403"
        subTitle="无权限访问该页面"
        extra={
          <Button type="primary" href="/dashboard">
            返回仪表盘
          </Button>
        }
      />
    );
  }
  return <>{children}</>;
};
