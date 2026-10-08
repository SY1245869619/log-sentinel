import { Button, Form, Input, message, Select, Space, Typography } from 'antd';
import React, { useState } from 'react';

/**
 * 日志行首样本 → 多行起始正则。
 * 粘贴一条日志的开头（如 2026-09-29 10:43:10,223 或 [2026-09-28 12:24:00.291]），
 * 自动识别日期/时间/数字并生成正则，填入目标字段。
 */
export const SampleRegexGenerator: React.FC<{ target: string }> = ({ target }) => {
  const form = Form.useFormInstance();
  const [sample, setSample] = useState('');

  const generate = () => {
    const s = sample.trim();
    if (!s) {
      message.warning('请先粘贴日志开头样本');
      return;
    }
    form.setFieldsValue({ [target]: sampleToRegex(s) });
    message.success('已生成并填入');
  };

  return (
    <Space.Compact style={{ width: '100%', marginBottom: 4 }}>
      <Input
        placeholder="粘贴日志开头样本，如 2026-09-29 10:43:10,223 或 [2026-09-28 12:24:00.291]"
        value={sample}
        onChange={(e) => setSample(e.target.value)}
      />
      <Button type="primary" ghost onClick={generate}>
        生成正则
      </Button>
    </Space.Compact>
  );
};

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const TOKEN_RE = /(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)|(\d{4}-\d{2}-\d{2})|(\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)|(\d+)/;

function tokenToRegex(m: RegExpExecArray): string {
  if (m[1]) {
    return m[1].includes('T')
      ? '\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:[.,]\\d+)?'
      : '\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}(?:[.,]\\d+)?';
  }
  if (m[2]) return '\\d{4}-\\d{2}-\\d{2}';
  if (m[3]) return '\\d{2}:\\d{2}:\\d{2}(?:[.,]\\d+)?';
  return '\\d+';
}

/**
 * 日志头样本 → 行首正则。
 * 只取「字面量前缀 + 第一个时间/数字 token」：
 * 保证任何级别/模块的新日志行都能命中（多行合并的起点判定）。
 */
export function sampleToRegex(sample: string): string {
  const m = TOKEN_RE.exec(sample);
  if (!m) return '^';
  return '^' + escapeRegExp(sample.slice(0, m.index)) + tokenToRegex(m);
}

const CODE_STYLES = [
  { value: 'number', label: '纯数字码（如 500、402037047）' },
  { value: 'json', label: 'JSON 格式（"code": 402037047）' },
  { value: 'alpha', label: '字母业务码（如 ERR_TIMEOUT）' },
];

/** 错误码提取正则生成器：读取上方「错误码」字段的值 */
export const ErrorCodeGenerator: React.FC = () => {
  const form = Form.useFormInstance();
  const [style, setStyle] = useState('number');

  const generate = () => {
    const code = String(form.getFieldValue('code') || '').trim();
    if (!code) {
      message.warning('请先填写错误码');
      return;
    }
    const escaped = escapeRegExp(code);
    let regex = '';
    if (style === 'number') regex = `(?<!\\d)${escaped}(?!\\d)`;
    else if (style === 'json') regex = `"code":\\s*${escaped}`;
    else regex = `(?<![A-Z0-9_])${escaped}(?![A-Z0-9_])`;
    form.setFieldsValue({ extract_regex: regex });
    message.success('已生成并填入');
  };

  return (
    <Space style={{ marginBottom: 4 }} wrap>
      <Typography.Text type="secondary">提取正则生成：</Typography.Text>
      <Select size="small" style={{ width: 260 }} value={style} onChange={setStyle} options={CODE_STYLES} />
      <Button size="small" type="primary" ghost onClick={generate}>
        按错误码生成
      </Button>
    </Space>
  );
};
