import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart, FunnelChart } from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  FunnelChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  CanvasRenderer,
]);

/** Thin binding to ECharts' tree-shakeable core - see PROJECT_PLAN.md Phase
 * 9.5's ChartCard idea. Only the chart/component types actually used above
 * are registered, so the bundle carries a fraction of the full echarts
 * package. No echarts-for-react wrapper dependency; this is the whole
 * binding. */
export function EChart({ option, height = 280 }: { option: EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(option)]);

  return <div ref={ref} style={{ height }} />;
}
