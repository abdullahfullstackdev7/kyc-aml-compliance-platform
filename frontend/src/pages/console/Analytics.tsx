import type { EChartsOption } from "echarts";
import { useApi } from "@/lib/useApi";
import type {
  FunnelData,
  RoutingDatum,
  ScreeningVolumeDatum,
  SlaData,
  LlmUsageData,
} from "@/lib/types";
import { ChartCard } from "@/components/console/ChartCard";
import { EChart } from "@/components/console/EChart";

const BRAND_COLORS = ["#0FA3B1", "#123B6D", "#F2A541", "#C8102E", "#1F8A5B", "#0B1F3A"];

export default function Analytics() {
  const funnel = useApi<FunnelData>("/api/v1/analytics/funnel");
  const routing = useApi<RoutingDatum[]>("/api/v1/analytics/routing");
  const volume = useApi<ScreeningVolumeDatum[]>("/api/v1/analytics/screening-volume");
  const sla = useApi<SlaData>("/api/v1/analytics/sla");
  const llm = useApi<LlmUsageData>("/api/v1/analytics/llm-usage");

  const funnelOption: EChartsOption | null = funnel.data
    ? {
        color: BRAND_COLORS,
        tooltip: { trigger: "item" },
        series: [
          {
            type: "funnel",
            left: "6%",
            width: "88%",
            label: { formatter: "{b}: {c}" },
            data: [
              { name: "Submitted", value: funnel.data.submitted },
              { name: "Docs verified", value: funnel.data.docs_verified },
              { name: "Screened", value: funnel.data.screened },
              { name: "Decided", value: funnel.data.decided },
            ],
          },
        ],
      }
    : null;

  const routingOption: EChartsOption | null = routing.data
    ? {
        color: BRAND_COLORS,
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: routing.data.map((r) => r.tier) },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: routing.data.map((r) => r.count), itemStyle: { borderRadius: 4 } }],
      }
    : null;

  const volumeOption: EChartsOption | null = volume.data
    ? {
        color: BRAND_COLORS,
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: volume.data.map((v) => v.date) },
        yAxis: { type: "value" },
        series: [{ type: "line", data: volume.data.map((v) => v.count), smooth: true, areaStyle: {} }],
      }
    : null;

  const slaOption: EChartsOption | null = sla.data
    ? {
        color: [BRAND_COLORS[3], BRAND_COLORS[4]],
        tooltip: { trigger: "item" },
        legend: { bottom: 0 },
        series: [
          {
            type: "pie",
            radius: ["45%", "70%"],
            data: [
              { name: "Breached", value: sla.data.breached },
              { name: "On track", value: sla.data.on_track },
            ],
          },
        ],
      }
    : null;

  const llmOption: EChartsOption | null = llm.data
    ? {
        color: BRAND_COLORS,
        tooltip: { trigger: "axis" },
        legend: { top: 0 },
        xAxis: {
          type: "category",
          data: [...new Set(llm.data.by_provider_status.map((d) => d.provider))],
        },
        yAxis: { type: "value" },
        series: [...new Set(llm.data.by_provider_status.map((d) => d.status))].map((status) => ({
          name: status,
          type: "bar",
          stack: "total",
          data: [...new Set(llm.data!.by_provider_status.map((d) => d.provider))].map((provider) => {
            const match = llm.data!.by_provider_status.find(
              (d) => d.provider === provider && d.status === status,
            );
            return match?.calls ?? 0;
          }),
        })),
      }
    : null;

  return (
    <div className="p-6 md:p-10">
      <h1 className="text-2xl font-semibold text-navy dark:text-white">Analytics</h1>
      <p className="mt-1 text-sm text-neutral-900/60 dark:text-white/60">
        Operational metrics computed from real onboarding, screening and LLM usage data for your
        tenant. Revenue analytics (Phase 9.3) is out of scope for this build.
      </p>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Applications funnel"
          description="Applications that ever reached each onboarding milestone, from the audit trail."
          loading={funnel.loading}
          error={funnel.error}
          empty={!!funnel.data && Object.values(funnel.data).every((v) => v === 0)}
        >
          {funnelOption && <EChart option={funnelOption} />}
        </ChartCard>

        <ChartCard
          title="Daily screening volume"
          description="Screening runs per day over the last 30 days."
          loading={volume.loading}
          error={volume.error}
          empty={volume.data?.length === 0}
        >
          {volumeOption && <EChart option={volumeOption} />}
        </ChartCard>

        <ChartCard
          title="Routing distribution"
          description="Current case counts by risk tier (Clear, Review, High Risk, Reject)."
          loading={routing.loading}
          error={routing.error}
          empty={routing.data?.length === 0}
        >
          {routingOption && <EChart option={routingOption} height={260} />}
        </ChartCard>

        <ChartCard
          title="SLA compliance"
          description="Open cases (Review/High Risk queues) that are past their SLA due date."
          loading={sla.loading}
          error={sla.error}
          empty={!!sla.data && sla.data.breached === 0 && sla.data.on_track === 0}
        >
          {slaOption && <EChart option={slaOption} height={260} />}
        </ChartCard>

        <ChartCard
          title="LLM usage"
          description="Case-summary and decision-rationale calls by provider and outcome (success, cached, fallback)."
          loading={llm.loading}
          error={llm.error}
          empty={llm.data?.total_calls === 0}
        >
          {llmOption && (
            <>
              <EChart option={llmOption} height={240} />
              <p className="mt-2 text-xs text-neutral-900/50 dark:text-white/50">
                Cache hit rate: {((llm.data?.cache_hit_rate ?? 0) * 100).toFixed(1)}% &middot;{" "}
                {llm.data?.total_calls ?? 0} total calls
              </p>
            </>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
