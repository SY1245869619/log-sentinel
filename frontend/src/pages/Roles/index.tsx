import { Form, Input, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { fmt } from '../../utils/format';

const BUILTIN = ['ADMIN', 'OPS', 'VIEWER'];

const Roles: React.FC = () => (
  <CrudPage
    title="角色管理"
    api="/roles"
    writeRoles={['ADMIN']}
    searchItems={null}
    columns={[
      { title: 'ID', dataIndex: 'id', width: 70 },
      {
        title: '角色编码', dataIndex: 'code', width: 140,
        render: (v) => (
          <Tag color={BUILTIN.includes(v) ? 'processing' : 'default'}>
            {v}{BUILTIN.includes(v) ? '（内置）' : ''}
          </Tag>
        ),
      },
      { title: '角色名称', dataIndex: 'name', width: 160 },
      { title: '描述', dataIndex: 'description', ellipsis: true },
      { title: '创建时间', dataIndex: 'created_at', width: 170, render: fmt },
    ]}
    formItems={
      <>
        <Form.Item
          name="code"
          label="角色编码"
          rules={[
            { required: true, message: '请输入角色编码' },
            { pattern: /^[A-Z][A-Z0-9_]+$/, message: '大写字母开头，仅含大写字母/数字/下划线' },
          ]}
          extra="大写字母开头，如 AUDITOR"
        >
          <Input maxLength={32} placeholder="AUDITOR" />
        </Form.Item>
        <Form.Item name="name" label="角色名称" rules={[{ required: true, message: '请输入角色名称' }]}>
          <Input maxLength={64} placeholder="审计员" />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={2} maxLength={255} />
        </Form.Item>
      </>
    }
  />
);

export default Roles;
