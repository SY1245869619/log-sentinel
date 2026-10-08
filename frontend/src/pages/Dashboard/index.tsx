import {
  AlertOutlined, CheckCircleOutlined, CloseCircleOutlined, DatabaseOutlined,
  HddOutlined, ProjectOutlined, RocketOutlined,
} from '@ant-design/icons';
import { Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd';
import React, { useEffect, useState } from 'react';
import client from '../../api/client';
import EChart from '../../components/EChart';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const SEV_COLOR: Record<string, string> = {
  CRITICAL: '#ff4d4f', MAJOR: '#fa8c16', MINOR: '#1677ff',
};

const Dashboard: React.FC = () => {
  const [data, setData] = useState<any>(null);
  // 仅首次加载显示骨架屏，定时刷新静默更新，避免页面抖动
  const [initialLoading, setInitialLoading] = useState(true);

  const load = async () => {
    try {
      setData(await client.get('/dashboard'));
    } finally {
      setInitialLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, []);

  const d = data || {};
  const levels = d.level_distribution || [];

  const statCards = [
    { title: '今日告警数', value: d.today_alerts ?? 0, icon: <AlertOutlined />, color: '#faad14' },
    { title: '今日通知数', value: d.today_notifies ?? 0, icon: <CheckCircleOutlined />, color: '#52c41a' },
    { title: '今日通知失败数', value: d.today_notify_fails ?? 0, icon: <CloseCircleOutlined />, color: '#ff4d4f' },
    { title: '项目 / 主机', value: `${d.total_projects ?? 0} / ${d.total_hosts ?? 0}`, icon: <ProjectOutlined />, color: '#1677ff' },
    { title: '日志源', value: d.total_log_sources ?? 0, icon: <DatabaseOutlined />, color: '#722ed1' },
    { title: '运行中采集', value: d.running_collectors ?? 0, icon: <RocketOutlined />, color: '#13c2c2' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={[16, 16]}>
        {statCards.map((c) => (
          <Col xs={12} md={8} xl={4} key={c.title}>
            <Card loading={initialLoading}>
              <Statistic
                title={c.title} value={c.value}
                prefix={React.cloneElement(c.icon, { style: { color: c.color } })}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16}>
        <Col xs={24} xl={10}>
          <Card title="告警趋势（近 7 天）" loading={initialLoading} styles={{ body: { height: 320 } }}>
            <EChart
              height={280}
              option={{
                grid: { left: 40, right: 20, top: 30, bottom: 30 },
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: (d.trend || []).map((t: any) => t.date) },
                yAxis: { type: 'value', minInterval: 1 },
                series: [{
                  type: 'line', smooth: true, areaStyle: { opacity: 0.15 },
                  data: (d.trend || []).map((t: any) => t.count),
                  itemStyle: { color: '#1677ff' },
                }],
              }}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} xl={7}>
          <Card title="告警级别分布（近 7 天）" loading={initialLoading} styles={{ body: { height: 320 } }}>
            {levels.length === 0 ? (
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Typography.Text type="secondary">暂无数据</Typography.Text>
              </div>
            ) : (
              <EChart
                height={280}
                option={{
                  tooltip: { trigger: 'item' },
                  legend: { bottom: 0 },
                  series: [{
                    type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'],
                    label: { formatter: '{c}' },
                    data: levels.map((l: any) => ({
                      name: statusText(l.severity), value: l.count,
                      itemStyle: { color: SEV_COLOR[l.severity] || '#999' },
                    })),
                  }],
                }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12} xl={7}>
          <Card title="Top 排行" loading={initialLoading} styles={{ body: { height: 320, overflow: 'auto' } }}>
            <Row gutter={16}>
              <Col span={12}>
                <Typography.Text strong style={{ fontSize: 13 }}>项目（告警数）</Typography.Text>
                {(d.top_projects || []).length === 0 && (
                  <div style={{ padding: '12px 0' }}>
                    <Typography.Text type="secondary">暂无数据</Typography.Text>
                  </div>
                )}
                {(d.top_projects || []).map((p: any, i: number) => (
                  <div key={p.project_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {i + 1}. {p.project_name || `#${p.project_id}`}
                    </span>
                    <Tag color="warning">{p.count}</Tag>
                  </div>
                ))}
              </Col>
              <Col span={12}>
                <Typography.Text strong style={{ fontSize: 13 }}>错误码</Typography.Text>
                {(d.top_error_codes || []).length === 0 && (
                  <div style={{ padding: '12px 0' }}>
                    <Typography.Text type="secondary">暂无数据</Typography.Text>
                  </div>
                )}
                {(d.top_error_codes || []).map((c: any, i: number) => (
                  <div key={c.error_code} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {i + 1}. {c.error_code}
                    </span>
                    <Tag color="error">{c.count}</Tag>
                  </div>
                ))}
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} xl={12}>
          <Card
            title="采集异常"
            loading={initialLoading}
            extra={<HddOutlined style={{ color: '#52c41a' }} />}
          >
            <Table
              rowKey="log_source_id"
              size="small"
              dataSource={d.collector_issues || []}
              pagination={false}
              locale={{ emptyText: '采集运行正常' }}
              columns={[
                { title: '日志源', dataIndex: 'log_source_id', width: 80, render: (v) => `#${v}` },
                {
                  title: '状态', dataIndex: 'status', width: 90,
                  render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
                },
                { title: '延迟', dataIndex: 'delay_seconds', width: 80, render: (v) => (v != null ? `${v}s` : '-') },
                { title: '重连', dataIndex: 'retry_count', width: 60 },
                { title: '错误信息', dataIndex: 'error_msg', ellipsis: true },
                { title: '最后心跳', dataIndex: 'last_heartbeat', width: 150, render: fmt },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="最近告警" loading={initialLoading}>
            <Table
              rowKey="id"
              size="small"
              dataSource={d.recent_alerts || []}
              pagination={false}
              locale={{ emptyText: '暂无告警' }}
              columns={[
                { title: '规则', dataIndex: 'rule_name', ellipsis: true },
                { title: '项目', dataIndex: 'project_name', ellipsis: true },
                {
                  title: '级别', dataIndex: 'severity', width: 80,
                  render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
                },
                {
                  title: '状态', dataIndex: 'status', width: 90,
                  render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
                },
                { title: '时间', dataIndex: 'created_at', width: 150, render: fmt },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
