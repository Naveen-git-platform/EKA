"use client"

import { Canvas, useFrame } from "@react-three/fiber"
import { useEffect, useMemo, useRef } from "react"
import type { Group } from "three"

import { createDiscTexture } from "@/components/three/disc-texture"
import { fibonacciSphere } from "@/lib/insights/map"

function gradientColors(
  positions: Float32Array,
  radius: number,
  from: [number, number, number],
  to: [number, number, number],
) {
  const out = new Float32Array(positions.length)
  for (let i = 0; i < positions.length; i += 3) {
    const t = (positions[i + 1] / radius + 1) / 2 // 0 at the bottom pole, 1 at the top
    out[i] = from[0] + (to[0] - from[0]) * t
    out[i + 1] = from[1] + (to[1] - from[1]) * t
    out[i + 2] = from[2] + (to[2] - from[2]) * t
  }
  return out
}

function PointShell({
  count,
  radius,
  size,
  from,
  to,
  spin,
}: {
  count: number
  radius: number
  size: number
  from: [number, number, number]
  to: [number, number, number]
  spin: number
}) {
  const ref = useRef<Group>(null)
  const texture = useMemo(() => createDiscTexture(), [])
  useEffect(() => () => texture.dispose(), [texture])
  const { positions, colors } = useMemo(() => {
    const p = fibonacciSphere(count, radius)
    return { positions: p, colors: gradientColors(p, radius, from, to) }
  }, [count, radius, from, to])

  useFrame((state, delta) => {
    const g = ref.current
    if (!g) return
    g.rotation.y += delta * spin
    // Gentle parallax toward the pointer.
    g.rotation.x += (state.pointer.y * 0.25 - g.rotation.x) * Math.min(1, delta * 2)
  })

  return (
    <group ref={ref}>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={size}
          map={texture}
          alphaTest={0.05}
          sizeAttenuation
          vertexColors
          transparent
          opacity={0.9}
          depthWrite={false}
        />
      </points>
    </group>
  )
}

const VIOLET: [number, number, number] = [0.55, 0.49, 0.96]
const CYAN: [number, number, number] = [0.22, 0.74, 0.97]
const MINT: [number, number, number] = [0.2, 0.83, 0.6]

/** A slowly turning "knowledge orb": two nested point shells. Decorative only. */
export default function HeroScene({ animate }: { animate: boolean }) {
  return (
    <Canvas
      camera={{ position: [0, 0, 6.2], fov: 45 }}
      dpr={[1, 1.5]}
      frameloop={animate ? "always" : "demand"}
      gl={{ antialias: false, alpha: true, powerPreference: "low-power" }}
      aria-hidden
    >
      <PointShell count={1400} radius={2.3} size={0.06} from={VIOLET} to={CYAN} spin={animate ? 0.07 : 0} />
      <PointShell count={450} radius={1.35} size={0.07} from={CYAN} to={MINT} spin={animate ? -0.12 : 0} />
    </Canvas>
  )
}
