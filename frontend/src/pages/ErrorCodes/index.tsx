import { Form, Input, Tag, Typography } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { ErrorCodeGenerator } from '../../components/RegexHelper';
import { fmt } from '../../utils/format';

const ErrorCodes: React.FC = () => (
  <CrudPage
    title="错误码配置"
    api="/error-codes"
    toggleField="enabled"
    initialValues={{ enabled: 1 }}
    searchItems={
      <Form.Item name="code">
        <Input placeholder="错误码" allowClear style={{ width: 200 }} />
      </Form.Item>
    }
    columns={[
      { title: 'ID', dataIndex: 'id', width: 70 },
      { title: '错误码', dataIndex: 'code', width: 140, render: (v) => <Tag color="error">{v}</Tag> },
      { title: '提取正则', dataIndex: 'extract_regex', ellipsis: true },
      { title: '描述', dataIndex: 'description', ellipsis: true },
      { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
    ]}
    formItems={
      <>
        <Form.Item name="code" label="错误码" rules={[{ required: true, message: '请输入错误码' }]}>
          <Input placeholder="如：500 / 402037047 / ERR_TIMEOUT" maxLength={64} />
        </Form.Item>
        <Form.Item label="提取正则生成" colon={false} style={{ marginBottom: 4 }}>
          <ErrorCodeGenerator />
        </Form.Item>
        <Form.Item
          name="extract_regex"
          label="提取正则"
          rules={[{ required: true, message: '请输入提取正则' }]}
          extra="从日志行提取候选码再精确比对，避免数字误中"
        >
          <Input placeholder="(?<!\d)500(?!\d)" maxLength={255} />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input maxLength={255} />
        </Form.Item>
      </>
    }
  />
);

export default ErrorCodes;
