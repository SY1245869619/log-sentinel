import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Button, Card, Form, message, Modal, Popconfirm, Space, Switch, Table,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { useCallback, useEffect, useState } from 'react';
import client from '../api/client';
import { hasRole } from '../store/auth';

export interface CrudPageProps<T = any> {
  title: string;
  api: string;
  columns: ColumnsType<T>;
  /** 新增/编辑弹窗中的表单项 */
  formItems?: React.ReactNode;
  /** 筛选区表单项（name 作为查询参数） */
  searchItems?: React.ReactNode;
  /** 页面顶部的使用引导（Alert） */
  pageTip?: React.ReactNode;
  /** 无写权限角色也可查看；默认 ADMIN/OPS 可写 */
  writeRoles?: string[];
  hideAdd?: boolean;
  hideEdit?: boolean;
  hideDelete?: boolean;
  initialValues?: Record<string, any>;
  /** 行记录 → 表单初始值（编辑时） */
  toFormValues?: (record: T) => any;
  /** 表单值 → 提交体 */
  toSubmitValues?: (values: any) => any;
  /** 行内扩展操作 */
  extraActions?: (record: T, reload: () => void) => React.ReactNode;
  /** 启用/停用快捷开关对应的字段名（如 enabled / status），设置后列表出现开关列 */
  toggleField?: string;
  /** 表格额外查询参数 */
  defaultParams?: Record<string, any>;
  /** 弹窗表单顶部扩展区（拿到 form 实例，可放"一键填充"按钮等） */
  formExtra?: (form: any) => React.ReactNode;
}

function CrudPage<T extends { id: number }>(props: CrudPageProps<T>) {
  const {
    title, api, columns, formItems, searchItems, pageTip,
    writeRoles = ['ADMIN', 'OPS'], hideAdd, hideEdit, hideDelete,
    initialValues, toFormValues, toSubmitValues, extraActions, defaultParams,
    toggleField, formExtra,
  } = props;

  const canWrite = hasRole(...writeRoles);
  const [data, setData] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<T | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [searchForm] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const filters = searchForm.getFieldsValue();
      const params: Record<string, any> = { page, size, ...defaultParams };
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') params[k] = v;
      });
      const res: any = await client.get(api, { params });
      setData(res.list || []);
      setTotal(res.total || 0);
    } finally {
      setLoading(false);
    }
  }, [api, page, size, defaultParams, searchForm]);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = (record: T) => {
    setEditing(record);
    setModalOpen(true);
  };

  const onSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const body = toSubmitValues ? toSubmitValues(values) : values;
      if (editing) {
        await client.put(`${api}/${editing.id}`, body);
        message.success('更新成功');
      } else {
        await client.post(api, body);
        message.success('创建成功');
      }
      setModalOpen(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (record: T) => {
    await client.delete(`${api}/${record.id}`);
    message.success('删除成功');
    load();
  };

  const onToggle = async (record: T, value: boolean) => {
    if (!toggleField) return;
    await client.put(`${api}/${record.id}`, { ...record, [toggleField]: value ? 1 : 0 });
    message.success(value ? '已启用' : '已停用');
    load();
  };

  const toggleCol = toggleField
    ? {
        title: '启用', key: '__toggle', width: 80,
        render: (_: any, record: T) => (
          <Switch
            size="small"
            checked={!!(record as any)[toggleField]}
            disabled={!canWrite}
            onChange={(v) => onToggle(record, v)}
          />
        ),
      }
    : null;

  const actionCol = {
    title: '操作',
    key: '__actions',
    width: 200,
    render: (_: any, record: T) => (
      <Space size="small" wrap>
        {extraActions?.(record, load)}
        {canWrite && !hideEdit && (
          <Button size="small" type="link" onClick={() => openEdit(record)}>
            编辑
          </Button>
        )}
        {canWrite && !hideDelete && (
          <Popconfirm title="确认删除该记录？" onConfirm={() => onDelete(record)}>
            <Button size="small" type="link" danger>
              删除
            </Button>
          </Popconfirm>
        )}
      </Space>
    ),
  };

  const showActions = extraActions || (canWrite && (!hideEdit || !hideDelete));
  const finalColumns = [
    ...columns,
    ...(toggleCol ? [toggleCol] : []),
    ...(showActions ? [actionCol] : []),
  ] as ColumnsType<T>;

  return (
    <Card
      title={title}
      extra={
        <Space>
          {searchItems && (
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
          )}
          {canWrite && !hideAdd && formItems && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增
            </Button>
          )}
        </Space>
      }
    >
      {pageTip}
      {searchItems && (
        <Form
          form={searchForm}
          layout="inline"
          style={{ marginBottom: 16, rowGap: 12 }}
          onFinish={() => {
            setPage(1);
            load();
          }}
        >
          {searchItems}
          <Form.Item>
            <Button color="blue" variant="filled" htmlType="submit">查询</Button>
          </Form.Item>
        </Form>
      )}
      <Table<T>
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={data}
        columns={finalColumns}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize: size,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, s) => {
            setPage(p);
            setSize(s);
          },
        }}
      />
      {formItems && (
        <Modal
          title={editing ? `编辑${title}` : `新增${title}`}
          open={modalOpen}
          onOk={onSave}
          onCancel={() => setModalOpen(false)}
          confirmLoading={saving}
          destroyOnHidden
          width={640}
        >
          {/* destroyOnHidden 保证每次打开都是全新挂载，
              initialValues 在挂载时生效，新增显默认值、编辑显原值 */}
          <Form
            form={form}
            layout="vertical"
            preserve={false}
            initialValues={
              editing
                ? (toFormValues ? toFormValues(editing) : editing)
                : (initialValues || {})
            }
          >
            {formExtra?.(form)}
            {formItems}
          </Form>
        </Modal>
      )}
    </Card>
  );
}

export default CrudPage;
