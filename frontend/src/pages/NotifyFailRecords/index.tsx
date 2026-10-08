import { Button, Form, message, Popconfirm, Select, Tag } from 'antd';
import React from 'react';
import client from '../../api/client';
import CrudPage from '../../components/CrudPage';
import { hasRole } from '../../store/auth';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const NotifyFailRecords: React.FC = () => {
  const canWrite = hasRole('ADMIN', 'OPS');
  return (
    <CrudPage
      title="通知失败记录（死信）"
      api="/notify-fail-records"
      hideAdd
      hideEdit
      hideDelete
      searchItems={
        <Form.Item name="status">
          <Select placeholder="状态" allowClear style={{ width: 150 }}
            options={['FAILED', 'RESEND_SUCCESS', 'RESEND_FAILED'].map((v) => ({ value: v, label: statusText(v) }))} />
        </Form.Item>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 80 },
        { title: '渠道', dataIndex: 'channel_name', width: 130 },
        { title: '告警ID', dataIndex: 'alert_id', width: 90, render: (v) => (v ? `#${v}` : '-') },
        { title: '失败原因', dataIndex: 'error_msg', width: 240, ellipsis: true },
        { title: '重试次数', dataIndex: 'retry_count', width: 90 },
        {
          title: '状态', dataIndex: 'status', width: 110,
          render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
        },
        { title: '重发时间', dataIndex: 'resent_at', width: 160, render: fmt },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmt },
      ]}
      extraActions={canWrite ? (record: any, reload) => (
        <Popconfirm
          title="确认按原内容人工重发？"
          onConfirm={async () => {
            try {
              await client.post(`/notify-fail-records/${record.id}/resend`);
              message.success('重发成功');
            } catch {
              /* 拦截器已提示 */
            }
            reload();
          }}
        >
          <Button size="small" type="link">人工重发</Button>
        </Popconfirm>
      ) : undefined}
    />
  );
};

export default NotifyFailRecords;
