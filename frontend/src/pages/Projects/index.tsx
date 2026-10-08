import { Alert, Form, Input, Select, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { useOptions } from '../../hooks/useOptions';
import { fmt } from '../../utils/format';

const Projects: React.FC = () => {
  const channelOptions = useOptions('/notify-channels', 'name');
  const mentionOptions = useOptions('/mentions', 'name');

  return (
    <CrudPage
      title="项目管理"
      api="/projects"
      toggleField="status"
      initialValues={{
        status: 1,
        notify_channel_id: channelOptions[0]?.value,
        default_mention_id: mentionOptions[0]?.value,
      }}
      pageTip={
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="项目 = 一个被监控的应用（如 fscr-order 订单服务）。只需要填项目名；告警发钉钉时 @ 谁，在「@人配置」加人后到这里选择。"
        />
      }
      searchItems={
        <Form.Item name="name">
          <Input placeholder="项目名" allowClear style={{ width: 180 }} />
        </Form.Item>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 70 },
        { title: '项目名', dataIndex: 'name' },
        { title: '负责人', dataIndex: 'owner', width: 100 },
        { title: '描述', dataIndex: 'description', ellipsis: true },
        { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
      ]}
      formItems={
        <>
          <Form.Item name="name" label="项目名"
            rules={[{ required: true, message: '请输入项目名' }]}
            extra="与日志目录对应的名字，如 fscr-order（日志在 /opt/fscr/app/logs/fscr-order/）">
            <Input placeholder="fscr-order" maxLength={128} />
          </Form.Item>
          <Form.Item name="owner" label="负责人（可选）">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="notify_channel_id" label="告警发送渠道（可选）"
            extra="不选则使用系统默认钉钉渠道">
            <Select allowClear showSearch optionFilterProp="label" options={channelOptions} />
          </Form.Item>
          <Form.Item name="default_mention_id" label="默认 @人（可选）"
            extra="规则没有单独指定 @人 时，@ 这里选的人">
            <Select allowClear showSearch optionFilterProp="label" options={mentionOptions} />
          </Form.Item>
          <Form.Item name="description" label="描述（可选）">
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
        </>
      }
    />
  );
};

export default Projects;
