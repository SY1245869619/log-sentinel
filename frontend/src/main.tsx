import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import useGlassTheme from './glassTheme';
import './styles/glass.css';

dayjs.locale('zh-cn');

const Root: React.FC = () => {
  const configProps = useGlassTheme();
  return (
    <ConfigProvider
      {...configProps}
      locale={zhCN}
      // 开启 antd CSS 变量：glassTheme 中 cssVar.colorXxx 引用必须依赖它才能解析，
      // 否则所有 color-mix 半透明背景失效（组件变纯白）
      theme={{ ...configProps.theme, cssVar: {} }}
    >
      <App />
    </ConfigProvider>
  );
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
