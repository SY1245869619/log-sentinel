import * as echarts from 'echarts';
import React, { useEffect, useRef } from 'react';

interface Props {
  option: echarts.EChartsOption;
  height?: number;
}

/** ECharts 封装：自动初始化、更新与尺寸自适应 */
const EChart: React.FC<Props> = ({ option, height = 300 }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts>();

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} style={{ height, width: '100%' }} />;
};

export default EChart;
