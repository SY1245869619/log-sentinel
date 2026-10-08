import { PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, message, Popconfirm, Select, Space, Typography } from 'antd';
import React, { useCallback, useEffect, useState } from 'react';
import client from '../../api/client';
import { hasRole } from '../../store/auth';
import { fmt } from '../../utils/format';

const STATUS_TEXT: Record<string, string> = {
  RUNNING: '运行中', STOPPED: '已停止', RETRYING: '重连中',
  ERROR: '异常', DISABLED: '已停用',
};

const STATUS_COLOR: Record<string, string> = {
  RUNNING: '#4ade80', STOPPED: '#94a3b8', RETRYING: '#fbbf24',
  ERROR: '#f87171', DISABLED: '#64748b',
};

/** 采集状态卡：主机 + 显示器样式，信息展示在"屏幕"上 */
const MonitorCard: React.FC<{ st: any; canWrite: boolean; onAction: (id: number, action: string) => void }> = ({
  st, canWrite, onAction,
}) => {
  const color = STATUS_COLOR[st.status] || '#94a3b8';
  const running = st.status === 'RUNNING';
  return (
    <div className="collector-host">
      <div className="collector-desk">
        {/* 显示器组件（屏幕 + 支架 + 底座） */}
        <div className="collector-display">
          <div className="collector-monitor">
            <div className="collector-screen">
              <div className="screen-title">
                <span className="screen-dot" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
                <span className="screen-name">{st.source_name || `#${st.log_source_id}`}</span>
                <span className="screen-status" style={{ color }}>{STATUS_TEXT[st.status] || st.status}</span>
              </div>
              <div className="screen-row">
                <span className="k">项目</span><span className="v">{st.project_name || '-'}</span>
                <span className="k">主机</span><span className="v">{st.host_ip || st.host_name || '-'}</span>
              </div>
              <div className="screen-row">
                <span className="k">路径</span>
                <span className="v path" title={st.path_pattern}>{st.path_pattern || '-'}</span>
              </div>
              <div className="screen-row">
                <span className="k">文件</span>
                <span className="v path" title={st.current_file}>{st.current_file || '-'}</span>
              </div>
              <div className="screen-row">
                <span className="k">Offset</span><span className="v">{st.read_offset ?? 0}</span>
                <span className="k">延迟</span><span className="v">{st.delay_seconds ?? 0}s</span>
              </div>
              <div className="screen-row">
                <span className="k">心跳</span><span className="v">{fmt(st.last_heartbeat)}</span>
                <span className="k">重连</span><span className="v">{st.retry_count ?? 0} 次</span>
              </div>
              {st.error_msg && (
                <div className="screen-error" title={st.error_msg}>⚠ {st.error_msg}</div>
              )}
            </div>
          </div>
          <div className="collector-stand" />
          <div className="collector-base" />
        </div>
        {/* 机架式服务器（刀片位 + 散热网孔 + 电源 + 状态灯） */}
        <div className="collector-server">
          <div className="srv-blades">
            {Array.from({ length: 16 }).map((_, i) => <i key={i} />)}
          </div>
          <div className="srv-vent" />
          <div className="srv-fans"><i /><i /></div>
          <div className="srv-psu"><i /><i /></div>
          <div className="srv-leds">
            <i style={{ background: running ? '#4ade80' : '#475569', boxShadow: running ? '0 0 6px #4ade80' : 'none' }} />
            <i style={{ background: st.status === 'ERROR' ? '#f87171' : '#475569', boxShadow: st.status === 'ERROR' ? '0 0 6px #f87171' : 'none' }} />
            <i style={{ background: st.status === 'RETRYING' ? '#fbbf24' : '#475569' }} />
          </div>
          <div className="srv-label">{st.host_ip || 'LOCAL'}</div>
          <div className="srv-power" style={running ? { borderColor: '#4ade80', boxShadow: '0 0 6px #4ade80' } : undefined} />
        </div>
      </div>
      {/* 操作区 */}
      <div className="collector-actions">
        {canWrite && st.status !== 'RUNNING' && (
          <Button size="small" color="green" variant="filled" icon={<PlayCircleOutlined />} onClick={() => onAction(st.id, 'start')}>
            启动
          </Button>
        )}
        {canWrite && st.status === 'RUNNING' && (
          <Popconfirm title="确认停止采集？" onConfirm={() => onAction(st.id, 'stop')}>
            <Button size="small" color="danger" variant="filled" icon={<PauseCircleOutlined />}>停止</Button>
          </Popconfirm>
        )}
        {canWrite && (
          <Popconfirm title="确认重启采集？" onConfirm={() => onAction(st.id, 'restart')}>
            <Button size="small" color="blue" variant="outlined" icon={<ReloadOutlined />}>重启</Button>
          </Popconfirm>
        )}
      </div>
    </div>
  );
};

const Collector: React.FC = () => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>();
  const canWrite = hasRole('ADMIN', 'OPS');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res: any = await client.get('/collector/status', {
        params: { page: 1, size: 200, status: status || undefined },
      });
      setData(res.list || []);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  const onAction = async (id: number, action: string) => {
    await client.post(`/collector/${id}/${action}`);
    message.success('操作成功');
    setTimeout(load, 1000);
  };

  return (
    <Card
      title="采集管理"
      loading={loading && data.length === 0}
      extra={
        <Space>
          <Select
            placeholder="状态" allowClear style={{ width: 120 }} value={status} onChange={setStatus}
            options={Object.entries(STATUS_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }
    >
      {data.length === 0 && !loading ? (
        <Typography.Text type="secondary">暂无采集任务，请在「日志源管理」配置并启用</Typography.Text>
      ) : (
        <div className="collector-grid">
          {data.map((st) => (
            <MonitorCard key={st.id} st={st} canWrite={canWrite} onAction={onAction} />
          ))}
        </div>
      )}
    </Card>
  );
};

export default Collector;
