import { DownloadOutlined, FullscreenOutlined } from '@ant-design/icons';
import {
  Button, Card, DatePicker, Descriptions, Drawer, Form, Input, message, Modal,
  Popconfirm, Select, Space, Table, Tag, Tooltip, Typography,
} from 'antd';
import dayjs from 'dayjs';
import React, { useCallback, useEffect, useState } from 'react';
import client from '../../api/client';
import { useOptions } from '../../hooks/useOptions';
import { hasRole } from '../../store/auth';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const { RangePicker } = DatePicker;

const ErrorLogs: React.FC = () => {
  const projectOptions = useOptions('/projects', 'name');
  const hostOptions = useOptions('/hosts', 'name');
  const canWrite = hasRole('ADMIN', 'OPS');

  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [expandContent, setExpandContent] = useState<any>(null);
  const [searchForm] = Form.useForm();

  /** 内容单元格：固定宽度 + 首行预览 + 悬浮提示 + 展开按钮 */
  const contentCell = (v: string, r: any) => {
    const firstLine = (v || '').split('\n')[0] || '-';
    return (
      <Space size={4} style={{ maxWidth: '100%' }}>
        <Tooltip title={firstLine} placement="topLeft">
          <Typography.Text ellipsis style={{ maxWidth: 260 }}>
            {firstLine}
          </Typography.Text>
        </Tooltip>
        <Button
          size="small"
          type="text"
          icon={<FullscreenOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            setExpandContent(r);
          }}
        />
      </Space>
    );
  };

  const buildParams = (override?: Record<string, any>) => {
    const values = { ...filters, ...override };
    const params: Record<string, any> = {};
    Object.entries(values).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      if (k === 'range' && Array.isArray(v) && v[0]) {
        params.start_time = v[0].format('YYYY-MM-DDT00:00:00');
        params.end_time = v[1].format('YYYY-MM-DDT23:59:59');
      } else if (k !== 'range') {
        params[k] = v;
      }
    });
    return params;
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res: any = await client.get('/error-logs', {
        params: { page, size, ...buildParams() },
      });
      setData(res.list || []);
      setTotal(res.total || 0);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, size, filters]);

  useEffect(() => { load(); }, [load]);

  const onExport = async () => {
    try {
      const blob: any = await client.get('/error-logs/export', {
        params: buildParams(), responseType: 'blob',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `error_logs_${dayjs().format('YYYYMMDDHHmmss')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch {
      /* 拦截器已提示 */
    }
  };

  const onBatchDelete = async () => {
    await client.post('/error-logs/batch-delete', { ids: selectedRowKeys });
    message.success('删除成功');
    setSelectedRowKeys([]);
    load();
  };

  return (
    <Card
      title="报错日志"
      extra={
        <Space>
          {canWrite && (
            <>
              <Button color="purple" variant="outlined" icon={<DownloadOutlined />} onClick={onExport}>导出 CSV</Button>
              <Popconfirm title={`确认删除选中的 ${selectedRowKeys.length} 条记录？`}
                onConfirm={onBatchDelete} disabled={!selectedRowKeys.length}>
                <Button color="danger" variant="filled" disabled={!selectedRowKeys.length}>批量删除</Button>
              </Popconfirm>
            </>
          )}
        </Space>
      }
    >
      <Form
        form={searchForm}
        layout="inline"
        style={{ marginBottom: 16, rowGap: 12 }}
        onFinish={(values) => { setFilters(values); setPage(1); }}
      >
        <Form.Item name="project_id">
          <Select placeholder="项目" allowClear showSearch optionFilterProp="label"
            style={{ width: 160 }} options={projectOptions} />
        </Form.Item>
        <Form.Item name="host_id">
          <Select placeholder="主机" allowClear showSearch optionFilterProp="label"
            style={{ width: 150 }} options={hostOptions} />
        </Form.Item>
        <Form.Item name="level">
          <Select placeholder="级别" allowClear style={{ width: 110 }}
            options={['ERROR', 'FATAL', 'WARN'].map((v) => ({ value: v }))} />
        </Form.Item>
        <Form.Item name="error_code">
          <Input placeholder="错误码" allowClear style={{ width: 120 }} />
        </Form.Item>
        <Form.Item name="keyword">
          <Input placeholder="关键字" allowClear style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="alert_status">
          <Select placeholder="告警状态" allowClear style={{ width: 130 }}
            options={['NOTIFIED', 'SUPPRESSED', 'RECORD_ONLY'].map((v) => ({ value: v, label: statusText(v) }))} />
        </Form.Item>
        <Form.Item name="range">
          <RangePicker />
        </Form.Item>
        <Form.Item>
          <Button color="blue" variant="filled" htmlType="submit">查询</Button>
        </Form.Item>
      </Form>

      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={data}
        scroll={{ x: 'max-content' }}
        rowSelection={canWrite ? {
          selectedRowKeys, onChange: setSelectedRowKeys,
        } : undefined}
        pagination={{
          current: page, pageSize: size, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, s) => { setPage(p); setSize(s); },
        }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '项目', dataIndex: 'project_name', width: 120, ellipsis: true },
          { title: '主机', dataIndex: 'host_name', width: 100, ellipsis: true },
          {
            title: '级别', dataIndex: 'level', width: 75,
            render: (v) => (v ? <Tag color="error">{v}</Tag> : '-'),
          },
          { title: '错误码', dataIndex: 'error_code', width: 100, ellipsis: true, render: (v) => v || '-' },
          { title: '关键字', dataIndex: 'keyword', width: 130, ellipsis: true, render: (v) => v || '-' },
          {
            title: '内容', dataIndex: 'optimized_content', width: 300,
            render: contentCell,
          },
          {
            title: '告警状态', dataIndex: 'alert_status', width: 90,
            render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
          },
          { title: '发生时间', dataIndex: 'occurred_at', width: 160, render: fmt },
          {
            title: '操作', key: 'op', width: 120, fixed: 'right',
            render: (_, r: any) => (
              <Space size="small">
                <Button size="small" type="link" onClick={() => setDetail(r)}>详情</Button>
                {canWrite && (
                  <Popconfirm title="确认删除？" onConfirm={async () => {
                    await client.delete(`/error-logs/${r.id}`);
                    message.success('删除成功');
                    load();
                  }}>
                    <Button size="small" type="link" danger>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />

      {/* 内容展开弹窗：格式化展示 */}
      <Modal
        title="日志内容"
        width={800}
        open={!!expandContent}
        footer={null}
        onCancel={() => setExpandContent(null)}
      >
        {expandContent && (
          <>
            <Typography.Text type="secondary">
              {expandContent.project_name} / {expandContent.host_name} / {expandContent.file_path} / {fmt(expandContent.occurred_at)}
            </Typography.Text>
            <pre
              style={{
                marginTop: 12, maxHeight: 480, overflow: 'auto',
                background: '#f5f5f5', padding: 12, borderRadius: 8,
                whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12,
              }}
            >
              {expandContent.optimized_content}
            </pre>
          </>
        )}
      </Modal>

      <Drawer
        title="报错详情"
        width={760}
        open={!!detail}
        onClose={() => setDetail(null)}
        styles={{ body: { paddingTop: 12 } }}
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered items={[
              { key: '1', label: '项目', children: detail.project_name },
              { key: '2', label: '主机', children: detail.host_name },
              { key: '3', label: '日志源', children: detail.log_source_name },
              { key: '4', label: '级别', children: detail.level || '-' },
              { key: '5', label: '错误码', children: detail.error_code || '-' },
              { key: '6', label: '关键字', children: detail.keyword || '-' },
              { key: '7', label: '文件', children: (
                <Typography.Text copyable style={{ wordBreak: 'break-all' }}>
                  {detail.file_path}
                </Typography.Text>
              ), span: 2 },
              { key: '8', label: '行号', children: detail.line_no ?? '-' },
              { key: '9', label: '发生时间', children: fmt(detail.occurred_at) },
              { key: '10', label: '告警状态', children: (
                <Tag color={STATUS_COLOR[detail.alert_status]}>{statusText(detail.alert_status)}</Tag>
              ) },
              { key: '11', label: '指纹', children: (
                <Typography.Text copyable type="secondary" style={{ fontSize: 12 }}>
                  {detail.fingerprint?.slice(0, 24)}…
                </Typography.Text>
              ) },
            ]} />
            <Typography.Title level={5} style={{ marginTop: 16 }}>优化后内容（已脱敏）</Typography.Title>
            <pre className="log-detail-pre">{detail.optimized_content}</pre>
            <Typography.Title level={5}>原始内容</Typography.Title>
            <pre className="log-detail-pre">{detail.raw_content}</pre>
          </>
        )}
      </Drawer>
    </Card>
  );
};

export default ErrorLogs;
