import {
  Alert, Button, Col, Form, Input, InputNumber, Row, Select, Switch, Tag, TimePicker, Typography,
} from 'antd';
import dayjs from 'dayjs';
import React from 'react';
import CrudPage from '../../components/CrudPage';
import { useOptions } from '../../hooks/useOptions';
import { fmt, STATUS_COLOR, statusText } from '../../utils/format';

const MATCH_TYPE_TEXT: Record<string, string> = {
  KEYWORD: '按关键字', REGEX: '按正则', ERROR_CODE: '按错误码', LOG_LEVEL: '按日志级别',
};

const TRIGGER_TEXT: Record<string, string> = {
  immediate: '立即告警（命中 1 次就通知）',
  window: 'N 秒内 M 次（短时间频繁报错才通知）',
  consecutive: '连续 N 次（连续出错才通知）',
};

const AlertRules: React.FC = () => {
  const sourceOptions = useOptions('/log-sources', 'name');
  const keywordOptions = useOptions('/keywords', 'name');
  const errorCodeOptions = useOptions('/error-codes', 'code');
  const mentionOptions = useOptions('/mentions', 'name');
  const templateOptions = useOptions('/notify-templates', 'name');

  return (
    <CrudPage
      title="告警规则"
      api="/alert-rules"
      toggleField="enabled"
      initialValues={{
        severity: 'MAJOR', match_type: 'KEYWORD', trigger_mode: 'immediate',
        alert_enabled: 1, enabled: 1, silence_seconds: 300,
        recover_notify: 0, recover_window_seconds: 300,
        aggregate_notify: 0, aggregate_window_seconds: 60,
        window_seconds: 60, threshold_count: 5, consecutive_count: 3,
        mention_id: mentionOptions[0]?.value,
        template_id: templateOptions[0]?.value,
      }}
      formExtra={(form) => (
        <div style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            ghost
            onClick={() =>
              form.setFieldsValue({
                name: '空指针异常告警',
                severity: 'MAJOR',
                log_source_ids: sourceOptions.slice(0, 1).map((o) => o.value),
                match_type: 'KEYWORD',
                keyword_ids: keywordOptions.slice(0, 1).map((o) => o.value),
                trigger_mode: 'immediate',
                silence_seconds: 300,
                alert_enabled: 1,
                recover_notify: 0,
                aggregate_notify: 0,
                enabled: 1,
                mention_id: mentionOptions[0]?.value,
                template_id: templateOptions[0]?.value,
              })
            }
          >
            一键填充示例（不会配就点我）
          </Button>
        </div>
      )}
      toFormValues={(r: any) => ({
        ...r,
        trigger_mode: r.window_seconds ? 'window' : r.consecutive_count ? 'consecutive' : 'immediate',
        window_seconds: r.window_seconds ?? 60,
        threshold_count: r.threshold_count ?? 5,
        consecutive_count: r.consecutive_count ?? 3,
        maintenance_start: r.maintenance_start ? dayjs(r.maintenance_start, 'HH:mm') : null,
        maintenance_end: r.maintenance_end ? dayjs(r.maintenance_end, 'HH:mm') : null,
      })}
      toSubmitValues={(v) => {
        const body: any = {
          ...v,
          maintenance_start: v.maintenance_start ? v.maintenance_start.format('HH:mm') : null,
          maintenance_end: v.maintenance_end ? v.maintenance_end.format('HH:mm') : null,
        };
        delete body.trigger_mode;
        if (v.trigger_mode === 'immediate') {
          body.window_seconds = null; body.threshold_count = null; body.consecutive_count = null;
        } else if (v.trigger_mode === 'window') {
          body.consecutive_count = null;
        } else {
          body.window_seconds = null; body.threshold_count = null;
        }
        return body;
      }}
      pageTip={
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="告警规则：定义异常匹配条件、触发方式（立即 / N秒内M次 / 连续N次）、静默与通知策略。新增弹窗提供「一键填充示例」。"
        />
      }
      searchItems={
        <>
          <Form.Item name="name">
            <Input placeholder="规则名称" allowClear style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="severity">
            <Select placeholder="级别" allowClear style={{ width: 120 }}
              options={['CRITICAL', 'MAJOR', 'MINOR'].map((s) => ({ value: s, label: statusText(s) }))} />
          </Form.Item>
        </>
      }
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        { title: '规则名称', dataIndex: 'name', width: 180, ellipsis: true },
        {
          title: '级别', dataIndex: 'severity', width: 80,
          render: (v) => <Tag color={STATUS_COLOR[v]}>{statusText(v)}</Tag>,
        },
        { title: '匹配类型', dataIndex: 'match_type', width: 90, render: (v) => MATCH_TYPE_TEXT[v] || v },
        {
          title: '触发方式', key: 'trigger', width: 130,
          render: (_, r: any) => {
            if (r.window_seconds) return `${r.window_seconds}秒内${r.threshold_count}次`;
            if (r.consecutive_count) return `连续 ${r.consecutive_count} 次`;
            return '立即告警';
          },
        },
        { title: '静默期', dataIndex: 'silence_seconds', width: 80, render: (v) => `${v}s` },
        {
          title: '恢复/聚合', key: 'ra', width: 100,
          render: (_, r: any) => (
            <>
              {!!r.recover_notify && <Tag color="success">恢复</Tag>}
              {!!r.aggregate_notify && <Tag color="processing">聚合</Tag>}
            </>
          ),
        },
        {
          title: '维护窗口', key: 'mw', width: 130,
          render: (_, r: any) => (r.maintenance_start ? `${r.maintenance_start}~${r.maintenance_end}` : '-'),
        },
        { title: '更新时间', dataIndex: 'updated_at', width: 155, render: fmt },
      ]}
      formItems={
        <>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入名称' }]}
                extra="如：订单服务-空指针告警">
                <Input maxLength={128} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="severity" label="严重级别" rules={[{ required: true }]}>
                <Select options={[
                  { value: 'CRITICAL', label: '严重（半夜也要叫人）' },
                  { value: 'MAJOR', label: '重要（工作时间尽快处理）' },
                  { value: 'MINOR', label: '次要（知道就行）' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="log_source_ids" label="关联日志源"
            rules={[{ required: true, message: '至少选择一个日志源' }]}
            extra="可多选">
            <Select mode="multiple" showSearch optionFilterProp="label" options={sourceOptions} />
          </Form.Item>
          <Form.Item name="match_type" label="按什么匹配异常" rules={[{ required: true }]}>
            <Select options={Object.entries(MATCH_TYPE_TEXT).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item shouldUpdate={(a: any, b: any) => a.match_type !== b.match_type} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) => {
              const type = getFieldValue('match_type');
              if (type === 'KEYWORD') {
                return (
                  <Form.Item name="keyword_ids" label="勾选关键字（在「4.关键字配置」里维护）"
                    rules={[{ required: true, message: '至少勾选一个关键字' }]}>
                    <Select mode="multiple" showSearch optionFilterProp="label" options={keywordOptions} />
                  </Form.Item>
                );
              }
              if (type === 'ERROR_CODE') {
                return (
                  <Form.Item name="error_code_ids" label="勾选错误码（在「5.错误码配置」里维护）"
                    rules={[{ required: true, message: '至少勾选一个错误码' }]}>
                    <Select mode="multiple" showSearch optionFilterProp="label" options={errorCodeOptions} />
                  </Form.Item>
                );
              }
              return (
                <Form.Item name="match_content"
                  label={type === 'LOG_LEVEL' ? '日志级别' : '正则表达式（进阶，一般用关键字即可）'}
                  rules={[{ required: true, message: '请输入匹配内容' }]}>
                  {type === 'LOG_LEVEL' ? (
                    <Select options={['ERROR', 'FATAL', 'WARN'].map((s) => ({ value: s }))} />
                  ) : (
                    <Input placeholder="如 OutOfMemoryError|StackOverflowError" maxLength={512} />
                  )}
                </Form.Item>
              );
            }}
          </Form.Item>
          <Form.Item name="trigger_mode" label="触发方式" rules={[{ required: true }]}>
            <Select options={Object.entries(TRIGGER_TEXT).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item shouldUpdate={(a: any, b: any) => a.trigger_mode !== b.trigger_mode} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) => {
              const mode = getFieldValue('trigger_mode');
              if (mode === 'window') {
                return (
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="window_seconds" label="N（秒）" rules={[{ required: true, message: '必填' }]}>
                        <InputNumber min={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="threshold_count" label="M（次）" rules={[{ required: true, message: '必填' }]}>
                        <InputNumber min={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                );
              }
              if (mode === 'consecutive') {
                return (
                  <Form.Item name="consecutive_count" label="连续 N 次" rules={[{ required: true, message: '必填' }]}>
                    <InputNumber min={1} style={{ width: 200 }} />
                  </Form.Item>
                );
              }
              return null;
            }}
          </Form.Item>
          <Form.Item name="silence_seconds" label="静默期（秒）"
            extra="触发后 N 秒内相同维度告警不再通知">
            <InputNumber min={0} style={{ width: 200 }} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="alert_enabled" label="发送通知" valuePropName="checked"
                getValueProps={(v) => ({ checked: !!v })} getValueFromEvent={(v) => (v ? 1 : 0)}
                extra="关闭=只记录不通知">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="recover_notify" label="恢复通知" valuePropName="checked"
                getValueProps={(v) => ({ checked: !!v })} getValueFromEvent={(v) => (v ? 1 : 0)}
                extra="故障恢复后告知">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="aggregate_notify" label="聚合通知" valuePropName="checked"
                getValueProps={(v) => ({ checked: !!v })} getValueFromEvent={(v) => (v ? 1 : 0)}
                extra="多条合并成一条发">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item shouldUpdate={(a: any, b: any) => a.recover_notify !== b.recover_notify || a.aggregate_notify !== b.aggregate_notify} style={{ marginBottom: 0 }}>
            {({ getFieldValue }) => (
              <Row gutter={12}>
                {getFieldValue('recover_notify') ? (
                  <Col span={12}>
                    <Form.Item name="recover_window_seconds" label="多少秒无新报错算恢复（秒）">
                      <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                ) : null}
                {getFieldValue('aggregate_notify') ? (
                  <Col span={12}>
                    <Form.Item name="aggregate_window_seconds" label="聚合窗口（秒）">
                      <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                ) : null}
              </Row>
            )}
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="maintenance_start" label="维护窗口开始（HH:mm）"
                extra="窗口内只记录不通知，支持跨天">
                <TimePicker format="HH:mm" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="maintenance_end" label="维护窗口结束（HH:mm）">
                <TimePicker format="HH:mm" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="mention_id" label="@人"
                extra="优先级：规则级 > 主机级 > 项目默认">
                <Select allowClear showSearch optionFilterProp="label" options={mentionOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="template_id" label="通知模板"
                extra="不选则使用系统默认模板">
                <Select allowClear showSearch optionFilterProp="label" options={templateOptions} />
              </Form.Item>
            </Col>
          </Row>
        </>
      }
    />
  );
};

export default AlertRules;
