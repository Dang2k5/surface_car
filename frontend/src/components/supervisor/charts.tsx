import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const axis = {
  stroke: "var(--border-strong)",
  tick: { fill: "var(--muted-foreground)", fontSize: 10, fontFamily: "var(--font-mono)" },
  tickLine: false,
  axisLine: { stroke: "var(--border)" },
};

const tooltipStyle = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border-strong)",
    borderRadius: 3,
    fontSize: 11,
    fontFamily: "var(--font-mono)",
    color: "var(--foreground)",
  },
  labelStyle: { color: "var(--muted-foreground)", fontSize: 10 },
  cursor: { stroke: "var(--border-strong)", strokeWidth: 1 },
};

export type TrendPoint = { t: string; pass: number; fail: number; defectRate: number };

export function QualityStream({
  data,
  height = 300,
  onPointClick,
}: {
  data: TrendPoint[];
  height?: number;
  onPointClick?: (p: TrendPoint) => void;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart
        data={data}
        margin={{ top: 8, right: 8, left: -14, bottom: 0 }}
        onClick={(e: { activePayload?: { payload: TrendPoint }[] }) => {
          const p = e?.activePayload?.[0]?.payload;
          if (p && onPointClick) onPointClick(p);
        }}
      >
        <defs>
          <linearGradient id="gPass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--success)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--success)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="t" {...axis} minTickGap={26} />
        <YAxis yAxisId="left" {...axis} width={46} />
        <YAxis yAxisId="right" orientation="right" {...axis} width={40} unit="%" />
        <Tooltip {...tooltipStyle} />
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="pass"
          name="PASS"
          stroke="var(--success)"
          strokeWidth={1.4}
          fill="url(#gPass)"
        />
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="fail"
          name="FAIL"
          stroke="var(--destructive)"
          strokeWidth={1.4}
          fillOpacity={0.12}
          fill="var(--destructive)"
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="defectRate"
          name="Defect %"
          stroke="var(--warning)"
          strokeWidth={1.6}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function DefectRateTrend({ data, height = 210 }: { data: TrendPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="t" {...axis} minTickGap={30} />
        <YAxis {...axis} width={40} unit="%" />
        <Tooltip {...tooltipStyle} />
        <ReferenceLine
          y={2}
          stroke="var(--warning)"
          strokeDasharray="4 4"
          label={{ value: "mục tiêu 2.0%", fill: "var(--warning)", fontSize: 9, position: "right" }}
        />
        <Line
          type="monotone"
          dataKey="defectRate"
          name="Defect %"
          stroke="var(--destructive)"
          strokeWidth={1.6}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function PassFailBars({ data, height = 210 }: { data: TrendPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="t" {...axis} minTickGap={30} />
        <YAxis {...axis} width={46} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="pass" name="PASS" stackId="a" fill="var(--success)" fillOpacity={0.55} />
        <Bar dataKey="fail" name="FAIL" stackId="a" fill="var(--destructive)" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DonutChart({
  data,
  height = 210,
}: {
  data: { name: string; value: number; color: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius="56%"
          outerRadius="82%"
          paddingAngle={2}
          stroke="var(--surface)"
        >
          {data.map((d) => (
            <Cell key={d.name} fill={d.color} />
          ))}
        </Pie>
        <Tooltip {...tooltipStyle} cursor={false} />
        <Legend
          verticalAlign="bottom"
          height={28}
          formatter={(v: string) => (
            <span style={{ color: "var(--muted-foreground)", fontSize: 11 }}>{v}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function heatColor(rate: number) {
  if (rate >= 4) return "bg-destructive/85";
  if (rate >= 3) return "bg-destructive/55";
  if (rate >= 2.2) return "bg-warning/70";
  if (rate >= 1.6) return "bg-warning/40";
  if (rate >= 1.0) return "bg-info/35";
  return "bg-info/15";
}

export function HeatLegend({ className }: { className?: string }) {
  return (
    <div className={className ? className : "flex items-center gap-2"}>
      <span className="label-caps">Thấp</span>
      {[
        "bg-info/15",
        "bg-info/35",
        "bg-warning/40",
        "bg-warning/70",
        "bg-destructive/55",
        "bg-destructive/85",
      ].map((c) => (
        <span key={c} className={`h-3 w-5 rounded-[1px] ${c}`} />
      ))}
      <span className="label-caps">Cao</span>
    </div>
  );
}
