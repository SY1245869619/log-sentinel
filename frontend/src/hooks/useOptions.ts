import { useEffect, useState } from 'react';
import client from '../api/client';

export interface Option {
  label: string;
  value: number | string;
}

/** 加载下拉选项（分页接口前 200 条） */
export function useOptions(api: string, labelKey: string, valueKey = 'id'): Option[] {
  const [options, setOptions] = useState<Option[]>([]);
  useEffect(() => {
    client
      .get(api, { params: { page: 1, size: 200 } })
      .then((res: any) => {
        // 兼容分页响应 {list:[...]} 与纯列表响应 [...]
        const rows: any[] = Array.isArray(res) ? res : (res.list || []);
        setOptions(rows.map((x: any) => ({
          label: x[labelKey],
          value: x[valueKey],
        })));
      })
      .catch(() => setOptions([]));
  }, [api, labelKey, valueKey]);
  return options;
}
