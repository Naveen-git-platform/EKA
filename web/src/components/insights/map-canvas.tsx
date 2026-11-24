"use client"

import { OrbitControls } from "@react-three/drei"
import { Canvas, type ThreeEvent } from "@react-three/fiber"
import { useEffect, useMemo } from "react"
import type { CanvasTexture } from "three"

import { createDiscTexture } from "@/components/three/disc-texture"
import type { MapPoint } from "@/lib/api/schemas"
import { buildPointBuffers, pointSize, SCENE_RADIUS, type PointBuffers, type RetrievedIds } from "@/lib/insights/map"

export type HoverInfo = { index: number; x: number; y: number }

type Props = {
  points: MapPoint[]
  colors: Map<string, string>
  hiddenDocs: ReadonlySet<string>
  highlight: RetrievedIds | null
  autoRotate: boolean
  onHover: (info: HoverInfo | null) => void
  onSelect: (index: number | null) => void
}

type LayerProps = {
  texture: CanvasTexture
  buffers: PointBuffers
  size: number
  opacity: number
  interactive?: boolean
  onHover: Props["onHover"]
  onSelect: Props["onSelect"]
}

function Layer({ buffers, size, opacity, texture, interactive = true, onHover, onSelect }: LayerProps) {
  if (buffers.count === 0) return null
  const handlers = interactive
    ? {
        onPointerMove: (e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation()
          if (e.index === undefined) return
          onHover({ index: buffers.sourceIndex[e.index], x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY })
        },
        onPointerOut: () => onHover(null),
        onClick: (e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation()
          if (e.index !== undefined) onSelect(buffers.sourceIndex[e.index])
        },
      }
    : {}
  return (
    <points {...handlers}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[buffers.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[buffers.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={size}
        map={texture}
        alphaTest={0.05}
        sizeAttenuation
        vertexColors
        transparent
        opacity={opacity}
        depthWrite={false}
      />
    </points>
  )
}

/** The 3D scatter of chunk embeddings. Kept thin: all data shaping lives in `lib/insights/map.ts` and is unit-tested. */
export default function MapCanvas({ points, colors, hiddenDocs, highlight, autoRotate, onHover, onSelect }: Props) {
  const layers = useMemo(() => {
    const retrieved = highlight?.retrieved
    const cited = highlight?.cited
    const retrievedOnly = retrieved && cited ? new Set([...retrieved].filter((id) => !cited.has(id))) : undefined
    return {
      base: buildPointBuffers(points, { colors, hiddenDocs, exclude: retrieved }),
      retrieved: retrievedOnly
        ? buildPointBuffers(points, { colors, hiddenDocs, only: retrievedOnly, color: "#fbbf24" })
        : null,
      cited: cited ? buildPointBuffers(points, { colors, hiddenDocs, only: cited, color: "#ffffff" }) : null,
    }
  }, [points, colors, hiddenDocs, highlight])

  const texture = useMemo(() => createDiscTexture(), [])
  useEffect(() => () => texture.dispose(), [texture])
  const base = pointSize(layers.base.count + (layers.retrieved?.count ?? 0) + (layers.cited?.count ?? 0))
  const dim = !!highlight && highlight.retrieved.size > 0
  const key = `${layers.base.count}-${layers.retrieved?.count ?? 0}-${layers.cited?.count ?? 0}`

  return (
    <Canvas
      camera={{ position: [0, 0, 7], fov: 50 }}
      dpr={[1, 2]}
      raycaster={{ params: { Points: { threshold: 0.06 } } as never }}
      onPointerMissed={() => onSelect(null)}
      gl={{ antialias: true, alpha: true }}
    >
      <mesh>
        <icosahedronGeometry args={[SCENE_RADIUS * 1.02, 1]} />
        <meshBasicMaterial wireframe transparent opacity={0.035} color="#8b7cf6" />
      </mesh>
      <group key={key}>
        <Layer
          texture={texture}
          buffers={layers.base}
          size={base}
          opacity={dim ? 0.3 : 0.9}
          onHover={onHover}
          onSelect={onSelect}
        />
        {layers.retrieved && (
          <Layer
            texture={texture}
            buffers={layers.retrieved}
            size={base * 1.7}
            opacity={1}
            onHover={onHover}
            onSelect={onSelect}
          />
        )}
        {layers.cited && (
          <Layer
            texture={texture}
            buffers={layers.cited}
            size={base * 2.3}
            opacity={1}
            onHover={onHover}
            onSelect={onSelect}
          />
        )}
      </group>
      <OrbitControls
        enablePan={false}
        enableDamping
        autoRotate={autoRotate}
        autoRotateSpeed={0.5}
        minDistance={3}
        maxDistance={11}
      />
    </Canvas>
  )
}
