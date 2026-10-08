import { Form, Input, Select, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { useOptions } from '../../hooks/useOptions';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const Alerts: React.FC = () => {
  const projectOptions = useOptions('/projects', 'name');
  return (
    <CrudPage
      title="告警记录"
      api="/alerts"
      hideAdd
      hideEdit
      hideDelete
      searchItems={
        <>
          <Form.Item name="project_id">
            <Select placeholder="项目" allowClear showSearch optionFilterProp="label"
              style={{ width: 170 }} options={projectOptions} />
          </Form.Item>
          <Form.Item name="severity">
            <Select placeholder="级别" allowClear style={{ width: 120 }}
              options={['CRITICAL', 'MAJOR', 'MINOR'].map((v) => ({ value: v, label: statusText(v) }))} />
          </Form.Item>
          <Form.Item name="status">
            <Select placeholder="状态" allowClear style={{ width: 130 }}
              options={['NOTIFIED', 'SUPPRESSED', 'AGGREGATED', 'RECORD_ONLY'].map((v) => ({ value: v, label: statusText(v) }))} />
          </Form.Item>
        </>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 80 },
        { title: '规则', dataIndex: 'rule_name', width: 200, ellipsis: true },
        { title: '项目', dataIndex: 'project_name', width: 140 },
        {
          title: '级别', dataIndex: 'severity', width: 90,
          render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
        },
        {
          title: '状态', dataIndex: 'status', width: 100,
          render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
        },
        { title: '报错日志', dataIndex: 'error_log_id', width: 100, render: (v) => (v ? `#${v}` : '-') },
        { title: '通知时间', dataIndex: 'notified_at', width: 160, render: fmt },
        { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmt },
      ]}
    />
  );
};

export default Alerts;
