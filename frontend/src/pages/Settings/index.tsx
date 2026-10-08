import { DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Card, InputNumber, message, Popconfirm, Table, Tag, Typography, Upload } from 'antd';
import React, { useEffect, useState } from 'react';
import client from '../../api/client';
import { applyWallpaper, DEFAULT_WALLPAPER, resolveWallpaper, WALLPAPERS } from '../../utils/wallpaper';
import { getToken } from '../../store/auth';

/**
 * 系统设置（仅管理员）：运行参数 + 登录页壁纸（内置 3 款 + 自定义 CSS）。
 */
const Settings: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  const [readonly, setReadonly] = useState<Record<string, any>>({});
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [wallpaper, setWallpaper] = useState<string>(DEFAULT_WALLPAPER);
  const [images, setImages] = useState<{ name: string; url: string; size: number }[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const res: any = await client.get('/system/settings');
      setItems((res.items || []).filter((i: any) => i.key !== 'login_wallpaper'));
      setReadonly(res.readonly || {});
      setNote(res.note || '');
      const wp = (res.items || []).find((i: any) => i.key === 'login_wallpaper');
      setWallpaper(wp?.value || DEFAULT_WALLPAPER);
      const imgs: any = await client.get('/system/wallpapers');
      setImages(imgs || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (key: string, value: string) => {
    await client.put('/system/settings', { key, value: String(value) });
    message.success('设置成功，即时生效');
    if (key === 'login_wallpaper') applyWallpaper(value);
    load();
  };

  const switchTo = async (value: string) => {
    setWallpaper(value);
    await save('login_wallpaper', value);
  };

  /** 上传图片壁纸：后端保存并自动切换 */
  const onUpload = async (options: any) => {
    const form = new FormData();
    form.append('file', options.file);
    try {
      const res: any = await client.post('/system/wallpaper/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${getToken()}` },
      });
      message.success('壁纸已上传并应用');
      setWallpaper(res.url);
      applyWallpaper(res.url);
      load();
      options.onSuccess?.(res);
    } catch (e) {
      options.onError?.(e);
    }
  };

  const onDeleteImage = async (img: { name: string; url: string }) => {
    await client.delete(`/system/wallpapers/${img.name}`);
    message.success('已删除');
    if (wallpaper === img.url) {
      setWallpaper(DEFAULT_WALLPAPER);
      applyWallpaper(DEFAULT_WALLPAPER);
    }
    load();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="全局壁纸（登录页与全部页面背景）" loading={loading}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
          {Object.entries(WALLPAPERS).map(([key, w]) => (
            <div
              key={key}
              onClick={() => switchTo(key)}
              style={{
                width: 200, height: 120, borderRadius: 10, cursor: 'pointer',
                background: w.bg,
                border: wallpaper === key ? '3px solid #1677ff' : '2px solid rgba(255,255,255,0.6)',
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                display: 'flex', alignItems: 'flex-end', padding: 8,
                fontSize: 13, fontWeight: 500,
                color: key === 'dark' ? '#fff' : 'inherit',
              }}
            >
              {w.label}
            </div>
          ))}
          {images.map((img) => (
            <div
              key={img.name}
              className="wp-thumb"
              style={{
                position: 'relative', width: 200, height: 120, borderRadius: 10,
                cursor: 'pointer',
                background: `url("${img.url}") center / cover`,
                border: wallpaper === img.url ? '3px solid #1677ff' : '2px solid rgba(255,255,255,0.6)',
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              }}
              onClick={() => switchTo(img.url)}
            >
              {wallpaper !== img.url && (
                <Popconfirm title="删除这张壁纸？" onConfirm={() => onDeleteImage(img)}>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    className="wp-del"
                    style={{ position: 'absolute', top: 4, left: 4, zIndex: 2 }}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              )}
            </div>
          ))}
          <Upload
            accept=".jpg,.jpeg,.png,.webp,.gif"
            showUploadList={false}
            customRequest={onUpload}
          >
            <div className="wp-upload">
              <UploadOutlined style={{ fontSize: 22, opacity: 0.55 }} />
              <div style={{ marginTop: 6, fontSize: 13, opacity: 0.65 }}>点击上传图片</div>
            </div>
          </Upload>
        </div>
        <Typography.Text type="secondary">
          点击缩略图立即切换并全局生效；内置壁纸不可删除；鼠标悬停在已上传图片上才显示删除按钮，正在使用的壁纸不可删除。
          玻璃拟态需要配合有图案/渐变的背景才能呈现磨砂效果。
        </Typography.Text>
      </Card>

      <Card title="运行参数" loading={loading}>
        <Table
          rowKey="key"
          size="middle"
          pagination={false}
          dataSource={items}
          columns={[
            { title: '设置项', dataIndex: 'description', width: 240 },
            { title: '键', dataIndex: 'key', width: 240, render: (v) => <Tag>{v}</Tag> },
            {
              title: '值', dataIndex: 'value', width: 180,
              render: (v, r: any) => (
                <InputNumber
                  min={1}
                  defaultValue={Number(v)}
                  onBlur={(e) => {
                    const nv = Number((e.target as HTMLInputElement).value);
                    if (nv && nv !== Number(v)) save(r.key, String(nv));
                  }}
                />
              ),
            },
            {
              title: '来源', dataIndex: 'source', width: 100,
              render: (v) => <Tag color={v === 'db' ? 'processing' : 'default'}>{v === 'db' ? '数据库' : '环境变量'}</Tag>,
            },
          ]}
        />
        <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
          修改数值后点击输入框外（失焦）即保存。
        </Typography.Text>
      </Card>
      <Card title="只读配置（环境变量）" loading={loading}>
        <Table
          rowKey="key"
          size="middle"
          pagination={false}
          dataSource={Object.entries(readonly).map(([key, value]) => ({ key, value }))}
          columns={[
            { title: '键', dataIndex: 'key', width: 280, render: (v) => <Tag>{v}</Tag> },
            { title: '值', dataIndex: 'value' },
          ]}
        />
        {note && (
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
            {note}
          </Typography.Text>
        )}
      </Card>
    </div>
  );
};

export default Settings;
