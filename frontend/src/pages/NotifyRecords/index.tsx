import { Form, Select, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const NotifyRecords: React.FC = () => (
  <CrudPage
    title="通知记录"
    api="/notify-records"
    hideAdd
    hideEdit
    hideDelete
    searchItems={
      <Form.Item name="status">
        <Select placeholder="状态" allowClear style={{ width: 130 }}
          options={['SUCCESS', 'FAILED'].map((v) => ({ value: v, label: statusText(v) }))} />
      </Form.Item>
    }
    columns={[
      { title: 'ID', dataIndex: 'id', width: 80 },
      { title: '告警ID', dataIndex: 'alert_id', width: 90, render: (v) => (v ? `#${v}` : '-') },
      { title: '渠道', dataIndex: 'channel_name', width: 130 },
      { title: '渠道类型', dataIndex: 'channel_type', width: 100, render: (v) => v && <Tag>{v}</Tag> },
      {
        title: '状态', dataIndex: 'status', width: 90,
        render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
      },
      { title: '重试次数', dataIndex: 'retry_count', width: 90 },
      { title: '请求内容', dataIndex: 'request_body', ellipsis: true },
      { title: '响应/错误', dataIndex: 'error_msg', width: 200, ellipsis: true, render: (v, r: any) => v || r.response_body || '-' },
      { title: '时间', dataIndex: 'created_at', width: 160, render: fmt },
    ]}
  />
);

export default NotifyRecords;
