import { Button, Form, Input, InputNumber, message, Select, Switch, Tag } from 'antd';
import React from 'react';
import client from '../../api/client';
import CrudPage from '../../components/CrudPage';
import { fmt } from '../../utils/format';

const TYPE_TEXT: Record<string, string> = {
  dingtalk: '钉钉', email: '邮件', wecom: '企微(预留)', feishu: '飞书(预留)', webhook: 'Webhook(预留)',
};

const Channels: React.FC = () => {
  const testChannel = async (id: number) => {
    try {
      const res: any = await client.post(`/notify-channels/${id}/test`);
      message.success(res?.message || '测试消息发送成功');
    } catch {
      /* 拦截器已提示 */
    }
  };

  return (
    <CrudPage
      title="通知渠道"
      api="/notify-channels"
      writeRoles={['ADMIN']}
      toggleField="enabled"
      initialValues={{ type: 'dingtalk', enabled: 1, timeout: 5, port: 465 }}
      toFormValues={(r: any) => ({ ...r, ...(r.config || {}) })}
      toSubmitValues={(v) => {
        const { id, name, type, enabled, created_at, updated_at, ...config } = v;
        return { name, type, enabled, config };
      }}
      searchItems={
        <Form.Item name="type">
          <Select placeholder="类型" allowClear style={{ width: 160 }}
            options={Object.entries(TYPE_TEXT).map(([value, label]) => ({ value, label }))} />
        </Form.Item>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '名称', dataIndex: 'name' },
        { title: '类型', dataIndex: 'type', width: 110, render: (v) => <Tag color="processing">{TYPE_TEXT[v] || v}</Tag> },
        {
          title: '配置', dataIndex: 'config', ellipsis: true,
          render: (c: any, r: any) => (r.type === 'dingtalk' ? c?.webhook : c ? `${c.host || ''}:${c.port || ''} ${c.user || ''}` : '-'),
        },
        { title: '更新时间', dataIndex: 'updated_at', width: 155, render: fmt },
      ]}
      extraActions={(record: any) => (
        <Button size="small" type="link" onClick={() => testChannel(record.id)}>
          测试发送
        </Button>
      )}
      formItems={
        <>
          <Form.Item name="name" label="渠道名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="type" label="渠道类型" rules={[{ required: true }]}>
            <Select options={Object.entries(TYPE_TEXT).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item shouldUpdate={(a: any, b: any) => a.type !== b.type} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) => {
              const type = getFieldValue('type');
              if (type === 'dingtalk') {
                return (
                  <>
                    <Form.Item name="webhook" label="Webhook" rules={[{ required: true, message: '请输入 Webhook' }]}>
                      <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
                    </Form.Item>
                    <Form.Item name="secret" label="Secret 加签（编辑显示 ****** 表示不变）">
                      <Input.Password autoComplete="new-password" placeholder="SEC..." />
                    </Form.Item>
                    <Form.Item name="at_all" label="是否 @所有人" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="timeout" label="超时时间（秒）">
                      <InputNumber min={1} max={30} style={{ width: 160 }} />
                    </Form.Item>
                  </>
                );
              }
              if (type === 'email') {
                return (
                  <>
                    <Form.Item name="host" label="SMTP 服务器" rules={[{ required: true, message: '请输入 SMTP 服务器' }]}>
                      <Input placeholder="smtp.qq.com" />
                    </Form.Item>
                    <Form.Item name="port" label="端口（SSL）" rules={[{ required: true }]}>
                      <InputNumber min={1} max={65535} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item name="user" label="发件邮箱" rules={[{ required: true, message: '请输入发件邮箱' }]}>
                      <Input placeholder="xxx@qq.com" />
                    </Form.Item>
                    <Form.Item name="password" label="授权码（编辑显示 ****** 表示不变）">
                      <Input.Password autoComplete="new-password" />
                    </Form.Item>
                    <Form.Item name="to" label="收件人列表" rules={[{ required: true, message: '请输入收件人' }]}
                      getValueFromEvent={(v) => v}>
                      <Select mode="tags" open={false} placeholder="输入邮箱后回车" />
                    </Form.Item>
                  </>
                );
              }
              return <Tag color="warning">该渠道类型为后续扩展预留</Tag>;
            }}
          </Form.Item>
          <Form.Item name="enabled" label="是否启用" valuePropName="checked"
            getValueProps={(v) => ({ checked: !!v })} getValueFromEvent={(v) => (v ? 1 : 0)}>
            <Switch />
          </Form.Item>
        </>
      }
    />
  );
};

export default Channels;
