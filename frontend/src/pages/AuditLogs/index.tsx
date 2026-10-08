import { Form, Input, Select, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { fmt, STATUS_COLOR } from '../../utils/format';

const ACTIONS = ['LOGIN', 'LOGOUT', 'CREATE', 'UPDATE', 'DELETE', 'EXPORT',
  'TEST_SSH', 'TEST_CHANNEL', 'COLLECTOR_CTRL', 'RESEND', 'CHANGE_PASSWORD'];

const AuditLogs: React.FC = () => (
  <CrudPage
    title="操作审计"
    api="/audit-logs"
    hideAdd
    hideEdit
    hideDelete
    searchItems={
      <>
        <Form.Item name="username">
          <Input placeholder="用户名" allowClear style={{ width: 150 }} />
        </Form.Item>
        <Form.Item name="action">
          <Select placeholder="操作类型" allowClear style={{ width: 170 }}
            options={ACTIONS.map((v) => ({ value: v }))} />
        </Form.Item>
      </>
    }
    columns={[
      { title: 'ID', dataIndex: 'id', width: 80 },
      { title: '用户', dataIndex: 'username', width: 120 },
      { title: '操作', dataIndex: 'action', width: 150, render: (v) => <Tag>{v}</Tag> },
      { title: '对象', dataIndex: 'target', width: 220, ellipsis: true },
      { title: 'IP', dataIndex: 'ip', width: 130 },
      {
        title: '结果', dataIndex: 'result', width: 90,
        render: (v) => <Tag color={STATUS_COLOR[v]}>{v === 'SUCCESS' ? '成功' : '失败'}</Tag>,
      },
      { title: '详情', dataIndex: 'detail', ellipsis: true },
      { title: '时间', dataIndex: 'created_at', width: 160, render: fmt },
    ]}
  />
);

export default AuditLogs;
