"use client"

import "@xyflow/react/dist/style.css"

import { Handle, Position, ReactFlow, type NodeProps, type NodeTypes, type Node } from "@xyflow/react"
import { AlertTriangle, Compass, MessageSquareText, Search, ShieldCheck, type LucideIcon } from "lucide-react"
import { memo, useMemo } from "react"

import { buildTraceGraph, type NodeId, type TraceNodeData } from "@/lib/chat/trace-graph"
import type { RunTrace } from "@/lib/chat/types"
import { formatMs } from "@/lib/format"
import { cn } from "@/lib/utils"

const ICONS: Record<NodeId, LucideIcon> = {
  planner: Compass,
  retriever: Search,
  critic: ShieldCheck,
  answer: MessageSquareText,
}

const STATUS_STYLE: Record<TraceNodeData["status"], string> = {
  idle: "border-border bg-card text-muted-foreground",
  active: "border-primary bg-accent text-accent-foreground glow animate-pulse",
  done: "border-success/50 bg-card text-foreground",
  error: "border-destructive/60 bg-destructive/10 text-foreground",
}

export function AgentNode({ data }: NodeProps<Node<TraceNodeData>>) {
  const Icon = ICONS[data.id]
  return (
    <div
      data-status={data.status}
      className={cn("w-44 rounded-xl border px-3 py-2 text-xs shadow-sm transition-colors", STATUS_STYLE[data.status])}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />
      <Handle type="target" id="loop-in" position={Position.Bottom} style={{ left: "30%" }} className="!opacity-0" />
      <Handle type="source" id="loop-out" position={Position.Bottom} style={{ left: "70%" }} className="!opacity-0" />
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="text-sm font-semibold">{data.title}</span>
        {data.warn && <AlertTriangle className="text-warning ml-auto size-3.5" aria-label="Degraded" />}
        {data.ms !== null && !data.warn && <span className="text-muted-foreground ml-auto">{formatMs(data.ms)}</span>}
      </div>
      <p className="text-muted-foreground mt-1 truncate">{data.detail}</p>
    </div>
  )
}

const nodeTypes: NodeTypes = { agent: memo(AgentNode) }

type Props = { run: RunTrace | undefined; streaming: boolean }

/** The four agents as a flow diagram, lit up by the real events. Read-only: no dragging, panning or zooming. */
export default function TraceGraph({ run, streaming }: Props) {
  const { nodes, edges } = useMemo(() => buildTraceGraph(run, streaming), [run, streaming])
  return (
    <div
      className="bg-muted/20 w-full overflow-x-auto rounded-xl border"
      role="img"
      aria-label="Agent pipeline diagram"
    >
      <div className="h-44 min-w-[640px]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          defaultEdgeOptions={{ style: { strokeWidth: 1.5 } }}
        />
      </div>
    </div>
  )
}
