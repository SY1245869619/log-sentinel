import { Alert, Badge, Button, Collapse, Form, Input, InputNumber, message, Select, Tag } from 'antd';
import React from 'react';
import client from '../../api/client';
import CrudPage from '../../components/CrudPage';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const Hosts: React.FC = () => {
  const testSsh = async (id: number) => {
    try {
      const res: any = await client.post(`/hosts/${id}/test-ssh`);
      message.success(res?.message || 'SSH 连接成功');
    } catch {
      /* 拦截器已提示 */
    }
  };

  return (
    <CrudPage
      title="主机管理"
      api="/hosts"
      initialValues={{ ssh_port: 22, auth_type: 'PASSWORD', bastion_port: 2222, bastion_auth_type: 'PASSWORD' }}
      pageTip={
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="主机：被采集日志的目标服务器（SSH 连接信息为服务器操作系统账号）。无法直连的服务器可在弹窗底部配置跳板机（jumpserver）中转。"
        />
      }
      searchItems={
        <>
          <Form.Item name="name">
            <Input placeholder="主机名" allowClear style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="env">
            <Select placeholder="环境" allowClear style={{ width: 120 }}
              options={['dev', 'test', 'prod'].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="tag">
            <Input placeholder="标签" allowClear style={{ width: 140 }} />
          </Form.Item>
        </>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '主机名', dataIndex: 'name' },
        { title: 'IP', dataIndex: 'ip', width: 130 },
        { title: 'SSH端口', dataIndex: 'ssh_port', width: 90 },
        { title: '环境', dataIndex: 'env', width: 80 },
        { title: '标签', dataIndex: 'tags', width: 140, ellipsis: true },
        {
          title: '状态', dataIndex: 'status', width: 100,
          render: (v) => <Badge status={(STATUS_COLOR[v] || 'default') as any} text={statusText(v)} />,
        },
        { title: '最后检测', dataIndex: 'last_check_at', width: 160, render: fmt },
      ]}
      extraActions={(record: any, reload) =>
        record.host_type !== 'LOCAL' && (
          <Button size="small" type="link"
            onClick={async () => { await testSsh(record.id); reload(); }}>
            测试SSH
          </Button>
        )
      }
      formItems={
        <>
          <Form.Item name="name" label="主机名" rules={[{ required: true, message: '请输入主机名' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="ip" label="IP 地址" rules={[{ required: true, message: '请输入 IP' }]}>
            <Input placeholder="10.70.70.96" maxLength={64} />
          </Form.Item>
          <Form.Item name="ssh_port" label="SSH 端口" rules={[{ required: true }]}>
            <InputNumber min={1} max={65535} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="auth_type" label="认证方式" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'PASSWORD', label: '密码' },
                { value: 'KEY', label: '私钥' },
              ]}
            />
          </Form.Item>
          <Form.Item name="username" label="用户名">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item shouldUpdate={(a: any, b: any) => a.auth_type !== b.auth_type} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) =>
              getFieldValue('auth_type') === 'KEY' ? (
                <Form.Item name="private_key" label="私钥" extra="编辑时显示 ****** 表示不变">
                  <Input.TextArea rows={4} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
                </Form.Item>
              ) : (
                <Form.Item name="password" label="密码" extra="编辑时显示 ****** 表示不变">
                  <Input.Password autoComplete="new-password" />
                </Form.Item>
              )
            }
          </Form.Item>
          <Form.Item name="env" label="环境">
            <Select allowClear options={['dev', 'test', 'prod'].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="tags" label="标签" extra="多个标签用逗号分隔">
            <Input placeholder="订单,支付,核心" maxLength={255} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
          <Collapse
            ghost
            items={[
              {
                key: 'bastion',
                label: '跳板机/堡垒机（可选，服务器不能直连时展开填写）',
                children: (
                  <>
                    <Form.Item name="bastion_ip" label="跳板机 IP"
                      extra="jumpserver 填其 IP；需管理员为账号开通目标资产直连授权">
                      <Input placeholder="10.99.99.170" maxLength={64} />
                    </Form.Item>
                    <Form.Item name="bastion_port" label="跳板机端口"
                      extra="jumpserver SSH 入口默认 2222">
                      <InputNumber min={1} max={65535} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item name="bastion_username" label="跳板机用户名">
                      <Input maxLength={64} />
                    </Form.Item>
                    <Form.Item name="bastion_auth_type" label="跳板机认证方式">
                      <Select style={{ width: 160 }}
                        options={[{ value: 'PASSWORD', label: '密码' }, { value: 'KEY', label: '私钥' }]} />
                    </Form.Item>
                    <Form.Item shouldUpdate={(a: any, b: any) => a.bastion_auth_type !== b.bastion_auth_type} style={{ marginBottom: 0 }}>
                      {({ getFieldValue: get }) =>
                        get('bastion_auth_type') === 'KEY' ? (
                          <Form.Item name="bastion_key" label="私钥" extra="编辑时显示 ****** 表示不变">
                            <Input.TextArea rows={3} />
                          </Form.Item>
                          ) : (
                          <Form.Item name="bastion_password" label="密码" extra="编辑时显示 ****** 表示不变">
                            <Input.Password autoComplete="new-password" />
                          </Form.Item>
                          )
                      }
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </>
      }
    />
  );
};

export default Hosts;
