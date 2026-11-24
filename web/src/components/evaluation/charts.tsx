"use client"

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  XAxis,
  YAxis,
} from "recharts"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import type { Aggregate, EvaluationResult } from "@/lib/api/schemas"
import { byCategory, radarData, timeline } from "@/lib/eval/metrics"
import { formatPercent } from "@/lib/format"

function ChartCard({
  title,
  description,
  children,
  summary,
}: {
  title: string
  description: string
  children: React.ReactNode
  summary: React.ReactNode
}) {
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {children}
        {/* The same numbers as text, for screen readers and anyone who cannot see the chart. */}
        <div className="sr-only">{summary}</div>
      </CardContent>
    </Card>
  )
}

const radarConfig = { value: { label: "Score", color: "var(--chart-1)" } } satisfies ChartConfig

export function ScoreRadar({ aggregate }: { aggregate: Aggregate | undefined }) {
  const data = radarData(aggregate)
  return (
    <ChartCard
      title="Quality profile"
      description="The four RAG metrics for the selected results"
      summary={
        <ul aria-label="Quality profile values">
          {data.map((d) => (
            <li key={d.metric}>
              {d.label}: {d.missing ? "not available" : formatPercent(d.value)}
            </li>
          ))}
        </ul>
      }
    >
      <ChartContainer config={radarConfig} className="mx-auto aspect-square max-h-64">
        <RadarChart data={data} outerRadius="62%" margin={{ top: 16, right: 24, bottom: 16, left: 24 }}>
          <ChartTooltip content={<ChartTooltipContent hideLabel formatter={(v) => formatPercent(Number(v))} />} />
          <PolarGrid />
          <PolarAngleAxis dataKey="short" />
          <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
          <Radar dataKey="value" stroke="var(--color-value)" fill="var(--color-value)" fillOpacity={0.3} />
        </RadarChart>
      </ChartContainer>
    </ChartCard>
  )
}

const timelineConfig = {
  overall: { label: "Overall", color: "var(--chart-2)" },
  rolling: { label: "5-answer average", color: "var(--chart-1)" },
} satisfies ChartConfig

export function ScoreTimeline({ results }: { results: EvaluationResult[] }) {
  const data = timeline(results)
  return (
    <ChartCard
      title="Score over time"
      description="Each scored answer, with a moving average to show the trend"
      summary={
        <p>
          {data.length
            ? `${data.length} scored answers; latest overall ${formatPercent(data.at(-1)?.overall)}`
            : "No scored answers yet"}
        </p>
      }
    >
      {data.length === 0 ? (
        <p className="text-muted-foreground flex h-52 items-center justify-center text-sm">No scored answers yet.</p>
      ) : (
        <ChartContainer config={timelineConfig} className="h-52 w-full">
          <LineChart data={data} margin={{ left: -16, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="n" tickLine={false} axisLine={false} />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
            <Line
              dataKey="overall"
              type="monotone"
              stroke="var(--color-overall)"
              strokeWidth={1.5}
              dot={{ r: 2.5 }}
              strokeOpacity={0.7}
            />
            <Line dataKey="rolling" type="monotone" stroke="var(--color-rolling)" strokeWidth={2.5} dot={false} />
          </LineChart>
        </ChartContainer>
      )}
    </ChartCard>
  )
}

const categoryConfig = { overall: { label: "Overall", color: "var(--chart-3)" } } satisfies ChartConfig

export function CategoryBars({ results }: { results: EvaluationResult[] }) {
  const data = byCategory(results)
  return (
    <ChartCard
      title="By question type"
      description="Average overall score per category in the question set"
      summary={
        <ul aria-label="Scores by question type">
          {data.map((d) => (
            <li key={d.category}>
              {d.category}: {formatPercent(d.overall)} across {d.count} answers
            </li>
          ))}
        </ul>
      }
    >
      {data.length === 0 ? (
        <p className="text-muted-foreground flex h-52 items-center justify-center text-sm">No scored answers yet.</p>
      ) : (
        <ChartContainer config={categoryConfig} className="h-52 w-full">
          <BarChart data={data} margin={{ left: -16, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="category" tickLine={false} axisLine={false} />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
            <Bar dataKey="overall" fill="var(--color-overall)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ChartContainer>
      )}
    </ChartCard>
  )
}
