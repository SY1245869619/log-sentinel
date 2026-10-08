import { CloudServerOutlined, DeleteOutlined, FolderOpenOutlined, ReloadOutlined, ScanOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, List, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import client from '../../api/client';
import { hasRole } from '../../store/auth';
import { fmt } from '../../utils/format';

const Agents: React.FC = () => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<any>(null); // {agent, token, command}
  const [filesModal, setFilesModal] = useState<any>(null);
  const [installOs, setInstallOs] = useState<'linux' | 'windows'>('linux');
  const [form] = Form.useForm();
  const canWrite = hasRole('ADMIN', 'OPS');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await client.get('/agents') as any);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onCreate = async () => {
    const values = await form.validateFields();
    const agent: any = await client.post('/agents', values);
    const install: any = await client.get(`/agents/${agent.id}/install`, { params: { os: installOs } });
    setCreated({ agent, token: agent.token, command: install.command });
    setCreateOpen(false);
    form.resetFields();
    load();
  };

  const refreshInstall = async (agentId: number, osName: 'linux' | 'windows') => {
    setInstallOs(osName);
    const install: any = await client.get(`/agents/${agentId}/install`, { params: { os: osName } });
    setCreated((c: any) => ({ ...c, command: install.command }));
  };

  const onScan = async (record: any) => {
    await client.post(`/agents/${record.id}/scan`, { base_dir: '/' });
    message.success('扫描请求已下发，Agent 心跳后执行（约 30 秒）');
  };

  const onViewFiles = async (record: any) => {
    const res: any = await client.get(`/agents/${record.id}/files`);
    if (!res) {
      message.info('暂无扫描结果，请先发起扫描');
      return;
    }
    setFilesModal(res);
  };

  return (
    <Card
      title="Agent 管理（内网主机主动上报模式）"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          {canWrite && (
            <Button type="primary" icon={<CloudServerOutlined />} onClick={() => setCreateOpen(true)}>
              新增 Agent
            </Button>
          )}
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={[
          { title: '名称', dataIndex: 'name', width: 140 },
          { title: '主机名', dataIndex: 'hostname', width: 150, render: (v) => v || '-' },
          { title: 'IP', dataIndex: 'ip', width: 130, render: (v) => v || '-' },
          { title: '系统', dataIndex: 'os', width: 100, render: (v, r) => (v ? `${v}/${r.arch}` : '-') },
          { title: '版本', dataIndex: 'version', width: 90, render: (v) => v || '-' },
          {
            title: '状态', dataIndex: 'status', width: 100,
            render: (v) => (
              <Tag color={v === 'ONLINE' ? 'success' : 'default'}>{v === 'ONLINE' ? '在线' : '离线'}</Tag>
            ),
          },
          { title: '日志源', dataIndex: 'source_count', width: 80 },
          { title: '最后心跳', dataIndex: 'last_heartbeat', width: 160, render: fmt },
          {
            title: '操作', width: 220, render: (_, r: any) => (
              <Space>
                {canWrite && (
                  <Button size="small" type="link" icon={<ScanOutlined />} onClick={() => onScan(r)}>扫描</Button>
                )}
                <Button size="small" type="link" icon={<FolderOpenOutlined />} onClick={() => onViewFiles(r)}>文件</Button>
                {hasRole('ADMIN') && (
                  <Popconfirm title="确认删除该 Agent？关联日志源需先解除" onConfirm={async () => {
                    await client.delete(`/agents/${r.id}`);
                    message.success('已删除');
                    load();
                  }}>
                    <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />

      {/* 创建 Agent */}
      <Modal
        title="新增 Agent"
        open={createOpen}
        onOk={onCreate}
        onCancel={() => setCreateOpen(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="备注名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：订单服务-生产-01" maxLength={128} />
          </Form.Item>
          <Typography.Text type="secondary">
            创建后会生成一次性 Token 和一键安装命令，请立即保存。
          </Typography.Text>
        </Form>
      </Modal>

      {/* 创建成功：Token + 安装命令（仅展示一次） */}
      <Modal
        title="Agent 创建成功（Token 仅显示一次）"
        open={!!created}
        footer={<Button type="primary" onClick={() => setCreated(null)}>我已保存</Button>}
        onCancel={() => setCreated(null)}
        width={680}
      >
        {created && (
          <>
            <Typography.Title level={5}>Agent Key</Typography.Title>
            <Typography.Paragraph copyable code>{created.agent.agent_key}</Typography.Paragraph>
            <Typography.Title level={5}>Token（务必立即保存，关闭后无法再查看）</Typography.Title>
            <Typography.Paragraph copyable code>{created.token}</Typography.Paragraph>
            <Typography.Title level={5}>
              一键安装命令
              <Select
                size="small" value={installOs} style={{ marginLeft: 12, width: 110 }}
                onChange={(v) => refreshInstall(created.agent.id, v)}
                options={[{ value: 'linux', label: 'Linux' }, { value: 'windows', label: 'Windows' }]}
              />
            </Typography.Title>
            <Typography.Paragraph copyable code style={{ wordBreak: 'break-all' }}>
              {created.command}
            </Typography.Paragraph>
            <Typography.Text type="secondary">
              在目标主机执行后，Agent 自动注册上线，状态变为"在线"。
            </Typography.Text>
          </>
        )}
      </Modal>

      {/* 扫描结果 */}
      <Modal
        title={`扫描结果：${filesModal?.base_dir || ''}（${filesModal?.scanned_at || '-'}）`}
        open={!!filesModal}
        footer={null}
        onCancel={() => setFilesModal(null)}
        width={720}
      >
        <List
          size="small"
          dataSource={filesModal?.files || []}
          pagination={{ pageSize: 12, size: 'small' }}
          renderItem={(f: string) => <List.Item style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{f}</List.Item>}
        />
      </Modal>
    </Card>
  );
};

export default Agents;
