import { Form, Input, InputNumber, Select, Tag, Typography } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { useOptions } from '../../hooks/useOptions';
import { fmt } from '../../utils/format';

const SCOPE_TEXT: Record<string, string> = { PROJECT: '项目级', HOST: '主机级', RULE: '规则级' };

const Mentions: React.FC = () => {
  const hostOptions = useOptions('/hosts', 'name');

  return (
    <CrudPage
      title="@人配置"
      api="/mentions"
      initialValues={{ scope: 'PROJECT' }}
      pageTip={null}
      searchItems={
        <Form.Item name="name">
          <Input placeholder="姓名" allowClear style={{ width: 160 }} />
        </Form.Item>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 70 },
        { title: '姓名', dataIndex: 'name' },
        { title: '手机号', dataIndex: 'mobile', width: 150 },
        {
          title: '级别', dataIndex: 'scope', width: 100,
          render: (v) => <Tag>{SCOPE_TEXT[v] || v}</Tag>,
        },
        { title: '关联主机ID', dataIndex: 'ref_id', width: 110, render: (v) => v ?? '-' },
        { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
      ]}
      formItems={
        <>
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="张三" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="mobile"
            label="手机号"
            rules={[{ required: true, message: '钉钉 @ 人依赖手机号' }]}
            extra="钉钉机器人通过手机号 @ 群成员"
          >
            <Input placeholder="13800000000" maxLength={32} />
          </Form.Item>
          <Form.Item name="dingtalk_userid" label="钉钉用户ID（可选）"
            extra="留空则按手机号 @；查看路径：钉钉管理后台 → 通讯录 → 成员详情">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="scope" label="生效级别" rules={[{ required: true }]}
            extra="项目级：项目默认 @ 人；主机级：指定主机的告警 @ 此人；规则级：在告警规则中单独引用">
            <Select
              options={[
                { value: 'PROJECT', label: '项目级' },
                { value: 'HOST', label: '主机级' },
                { value: 'RULE', label: '规则级' },
              ]}
            />
          </Form.Item>
          <Form.Item shouldUpdate={(a: any, b: any) => a.scope !== b.scope} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) =>
              getFieldValue('scope') === 'HOST' ? (
                <Form.Item name="ref_id" label="关联主机"
                  rules={[{ required: true, message: '主机级必须选择主机' }]}
                  extra="该主机上的告警 @ 此人">
                  <Select showSearch optionFilterProp="label" options={hostOptions} />
                </Form.Item>
              ) : null
            }
          </Form.Item>
        </>
      }
      toSubmitValues={(v) => ({
        ...v,
        ref_id: v.scope === 'HOST' ? v.ref_id : null,
      })}
    />
  );
};

export default Mentions;
