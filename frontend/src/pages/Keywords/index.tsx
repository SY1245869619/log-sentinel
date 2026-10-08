import { Alert, Form, Input, Select, Tag } from 'antd';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { fmt } from '../../utils/format';

const OP_TEXT: Record<string, string> = {
  CONTAINS: '包含', NOT_CONTAINS: '不包含(白名单)', EQUALS: '等于', REGEX: '正则',
};

const Keywords: React.FC = () => (
  <CrudPage
    title="关键字配置"
    api="/keywords"
    toggleField="enabled"
    initialValues={{ match_op: 'CONTAINS', enabled: 1 }}
    pageTip={
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="关键字库：维护日志异常匹配词，供告警规则引用。常用示例：NullPointerException、OutOfMemoryError、Connection refused、timeout。"
      />
    }
    searchItems={
      <Form.Item name="name">
        <Input placeholder="名称" allowClear style={{ width: 200 }} />
      </Form.Item>
    }
    columns={[
      { title: 'ID', dataIndex: 'id', width: 70 },
      { title: '名称', dataIndex: 'name' },
      { title: '匹配内容', dataIndex: 'pattern', ellipsis: true },
      {
        title: '匹配方式', dataIndex: 'match_op', width: 140,
        render: (v) => <Tag>{OP_TEXT[v] || v}</Tag>,
      },
      { title: '更新时间', dataIndex: 'updated_at', width: 160, render: fmt },
    ]}
    formItems={
      <>
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="如：空指针异常" maxLength={128} />
        </Form.Item>
        <Form.Item name="pattern" label="匹配内容" rules={[{ required: true, message: '请输入匹配内容' }]}>
          <Input placeholder="如：NullPointerException" maxLength={512} />
        </Form.Item>
        <Form.Item name="match_op" label="匹配方式" rules={[{ required: true }]}
          extra="NOT_CONTAINS 为白名单：命中该词则不告警（排除已知无害报错）">
          <Select
            options={[
              { value: 'CONTAINS', label: '包含' },
              { value: 'NOT_CONTAINS', label: '不包含（白名单）' },
              { value: 'EQUALS', label: '等于' },
              { value: 'REGEX', label: '正则匹配' },
            ]}
          />
        </Form.Item>
      </>
    }
  />
);

export default Keywords;
