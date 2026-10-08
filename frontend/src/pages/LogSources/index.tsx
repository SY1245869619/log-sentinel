import { Alert, Form, Input, InputNumber, Select, Typography } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { SampleRegexGenerator } from '../../components/RegexHelper';
import { useOptions } from '../../hooks/useOptions';
import { fmt } from '../../utils/format';

const LogSources: React.FC = () => {
  const projectOptions = useOptions('/projects', 'name');
  const hostOptions = useOptions('/hosts', 'name');
  const agentOptions = useOptions('/agents', 'name');

  return (
    <CrudPage
      title="日志源管理"
      api="/log-sources"
      toggleField="enabled"
      initialValues={{
        collect_mode: 'SSH', encoding: 'UTF-8', interval_seconds: 5,
        multiline_pattern: '^\\[?\\d{4}-\\d{2}-\\d{2}', enabled: 1,
      }}
      pageTip={
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="路径支持通配符：* 任意文件、** 递归目录、{project} 项目目录占位符（如 /data/logs/{project}/*.log，一条配置监控目录下全部项目，项目按目录名自动识别创建）。"
        />
      }
      searchItems={
        <>
          <Form.Item name="project_id">
            <Select placeholder="项目" allowClear showSearch optionFilterProp="label"
              style={{ width: 180 }} options={projectOptions} />
          </Form.Item>
          <Form.Item name="name">
            <Input placeholder="日志源名称" allowClear style={{ width: 160 }} />
          </Form.Item>
        </>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '名称', dataIndex: 'name' },
        { title: '项目', dataIndex: 'project_name', width: 130 },
        { title: '主机', dataIndex: 'host_name', width: 120, render: (v, r: any) => v || r.host_ip },
        {
          title: '接入方式', dataIndex: 'collect_mode', width: 100,
          render: (v) => ({ SSH: 'SSH直连', LOCAL: '本机', AGENT: 'Agent上报' } as any)[v] || v,
        },
        { title: '日志路径', dataIndex: 'path_pattern', ellipsis: true },
        { title: '编码', dataIndex: 'encoding', width: 80 },
        { title: '间隔', dataIndex: 'interval_seconds', width: 70, render: (v) => `${v}s` },
        { title: '环境(继承主机)', dataIndex: 'env', width: 120, render: (v) => v || '-' },
        { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
      ]}
      formItems={
        <>
          <Form.Item name="collect_mode" label="接入方式" rules={[{ required: true }]}
            extra="SSH直连=服务端远程读取；Agent上报=内网主机安装 Agent 主动推送">
            <Select options={[
              { value: 'SSH', label: 'SSH 直连' },
              { value: 'LOCAL', label: '本机采集' },
              { value: 'AGENT', label: 'Agent 上报' },
            ]} style={{ width: 200 }} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(a: any, b: any) => a.collect_mode !== b.collect_mode}>
            {({ getFieldValue }) => (
              <>
                <Form.Item name="host_id" label="归属主机" rules={[{ required: true, message: '请选择主机' }]}
                  extra={getFieldValue('collect_mode') === 'AGENT' ? 'Agent 模式下仅作归属标记，不要求可 SSH' : undefined}>
                  <Select showSearch optionFilterProp="label" options={hostOptions} />
                </Form.Item>
                {getFieldValue('collect_mode') === 'AGENT' && (
                  <Form.Item name="agent_id" label="采集 Agent" rules={[{ required: true, message: '请选择 Agent' }]}
                    extra="先到「Agent管理」创建并安装，在线后即可采集">
                    <Select showSearch optionFilterProp="label" options={agentOptions} />
                  </Form.Item>
                )}
              </>
            )}
          </Form.Item>
          <Form.Item name="project_id" label="默认项目"
            extra="路径含 {project} 时，实际归属按目录名自动识别；此项作为兜底"
            rules={[{ required: true, message: '请选择项目' }]}>
            <Select showSearch optionFilterProp="label" options={projectOptions} />
          </Form.Item>
          <Form.Item name="name" label="日志源名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item
            name="path_pattern"
            label="日志路径"
            rules={[{ required: true, message: '请输入日志路径' }]}
            extra="支持 * 任意文件、** 递归目录、{project} 项目目录占位符"
          >
            <Input placeholder="/data/logs/{project}/*.log" maxLength={512} />
          </Form.Item>
          <Form.Item name="exclude_pattern" label="排除规则"
            extra="glob 语法，如 *-debug.log">
            <Input placeholder="*-debug.log" maxLength={512} />
          </Form.Item>
          <Form.Item name="encoding" label="文件编码" rules={[{ required: true }]}
            extra="日志中文乱码时选 GBK">
            <Select options={[{ value: 'UTF-8' }, { value: 'GBK' }]} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item label="多行起始正则生成" colon={false} style={{ marginBottom: 4 }}>
            <SampleRegexGenerator target="multiline_pattern" />
          </Form.Item>
          <Form.Item
            name="multiline_pattern"
            label="多行起始正则"
            rules={[{ required: true }]}
            extra="行首匹配该正则视为新日志行，其余行并入上一条（合并 Traceback 堆栈）"
          >
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item name="interval_seconds" label="采集间隔（秒）" rules={[{ required: true }]}>
            <InputNumber min={1} max={3600} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input maxLength={255} />
          </Form.Item>
        </>
      }
    />
  );
};

export default LogSources;
