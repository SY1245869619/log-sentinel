import { Alert, Form, Input, Select, Tag, Typography } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { fmt } from '../../utils/format';

const PLACEHOLDERS =
  '${project} ${host} ${env} ${level} ${time} ${errorCode} ${keyword} ${file} ${content} ${mentions}';

const Templates: React.FC = () => (
  <CrudPage
    title="通知模板"
    api="/notify-templates"
    toggleField="enabled"
    initialValues={{ channel_type: 'dingtalk', msg_type: 'markdown', enabled: 1 }}
    pageTip={
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="模板 = 告警钉钉消息的格式。系统已内置一个默认模板，什么都不用配就能用。想自定义格式才需要在这里改；配了多个模板后，在「告警规则」里为每条规则选择用哪个，不选就用默认。"
      />
    }
    columns={[
      { title: 'ID', dataIndex: 'id', width: 70 },
      { title: '名称', dataIndex: 'name' },
      { title: '渠道类型', dataIndex: 'channel_type', width: 110, render: (v) => <Tag>{v}</Tag> },
      { title: '消息类型', dataIndex: 'msg_type', width: 100 },
      { title: '模板内容', dataIndex: 'content_template', ellipsis: true },
      { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
    ]}
    formItems={
      <>
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input maxLength={128} />
        </Form.Item>
        <Form.Item name="channel_type" label="渠道类型" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'dingtalk', label: '钉钉' },
              { value: 'email', label: '邮件' },
              { value: 'wecom', label: '企业微信（预留）' },
              { value: 'feishu', label: '飞书（预留）' },
            ]}
          />
        </Form.Item>
        <Form.Item name="msg_type" label="消息类型" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'markdown', label: 'markdown（支持关键字加粗）' },
              { value: 'text', label: 'text（纯文本）' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="content_template"
          label="模板内容"
          rules={[{ required: true, message: '请输入模板内容' }]}
          extra={<Typography.Text type="secondary">占位符（发送时自动替换为真实内容）：{PLACEHOLDERS}。markdown 中 **词** 表示加粗。</Typography.Text>}
        >
          <Input.TextArea rows={10} />
        </Form.Item>
      </>
    }
  />
);

export default Templates;
