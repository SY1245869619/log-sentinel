import { Form, Input, Select, Switch, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { useOptions } from '../../hooks/useOptions';
import { fmt } from '../../utils/format';

const ROLE_COLOR: Record<string, string> = { ADMIN: 'error', OPS: 'warning', VIEWER: 'default' };

const Users: React.FC = () => {
  const roleOptions = useOptions('/roles', 'name');

  return (
    <CrudPage
      title="用户与权限"
      api="/users"
      writeRoles={['ADMIN']}
      initialValues={{ status: 1, role_ids: [] }}
      toFormValues={(u: any) => ({
        ...u,
        password: undefined,
        role_ids: (u.roles || []).map((r: any) => r.id),
      })}
      searchItems={
        <Form.Item name="username">
          <Input placeholder="用户名" allowClear style={{ width: 160 }} />
        </Form.Item>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 70 },
        { title: '用户名', dataIndex: 'username' },
        { title: '姓名', dataIndex: 'real_name', width: 110 },
        {
          title: '角色', dataIndex: 'roles', width: 200,
          render: (roles: any[]) => (roles || []).map((r) => (
            <Tag key={r.id} color={ROLE_COLOR[r.code]}>{r.name}</Tag>
          )),
        },
        {
          title: '状态', dataIndex: 'status', width: 80,
          render: (v) => <Tag color={v ? 'success' : 'default'}>{v ? '启用' : '禁用'}</Tag>,
        },
        { title: '最后登录', dataIndex: 'last_login_at', width: 160, render: fmt },
      ]}
      formItems={
        <>
          <Form.Item name="username" label="用户名"
            rules={[{ required: true, min: 2, message: '用户名至少 2 个字符' }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="password" label="密码（新增必填至少8位，编辑留空表示不变）"
            rules={[
              ({ getFieldValue }) => ({
                required: !getFieldValue('id'),
                message: '新增用户必须设置密码',
              }),
              { min: 8, message: '密码至少 8 位' },
            ]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="real_name" label="姓名">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="role_ids" label="角色" rules={[{ required: true, message: '请选择角色' }]}
            extra="角色在「系统管理-角色管理」中维护">
            <Select mode="multiple" options={roleOptions} placeholder="选择角色" />
          </Form.Item>
          <Form.Item name="status" label="是否启用" valuePropName="checked"
            getValueProps={(v) => ({ checked: !!v })}
            getValueFromEvent={(v) => (v ? 1 : 0)}>
            <Switch />
          </Form.Item>
        </>
      }
    />
  );
};

export default Users;
