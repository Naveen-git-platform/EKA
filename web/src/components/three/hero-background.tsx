"use client"

import { useReducedMotion } from "framer-motion"
import dynamic from "next/dynamic"
import { useEffect, useRef, useState } from "react"

import { useWebgl } from "@/components/three/use-webgl"

const HeroScene = dynamic(() => import("@/components/three/hero-scene"), { ssr: false })

/**
 * Decorative 3D backdrop for the landing page. Always renders a CSS glow underneath; the WebGL orb fades in on top
 * only when the browser supports it, and it stands still for people who prefer reduced motion. It is loaded lazily
 * and paused while scrolled out of view, so it never competes with the content.
 */
export function HeroBackground() {
  const webgl = useWebgl()
  const reduced = useReducedMotion()
  const box = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    const el = box.current
    if (!el || typeof IntersectionObserver === "undefined") return
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div
      ref={box}
      aria-hidden
      className="pointer-events-none absolute inset-x-0 top-0 h-[34rem] overflow-hidden"
      data-testid="hero-background"
    >
      <div className="from-primary/25 via-chart-2/10 absolute -top-24 right-[-10%] size-[34rem] rounded-full bg-radial to-transparent blur-3xl" />
      {webgl && visible && (
        <div className="absolute inset-y-0 right-[-12%] w-[75%] [mask-image:radial-gradient(closest-side,black_55%,transparent)] opacity-90 sm:right-[-4%] sm:w-[60%] lg:w-[52%]">
          <HeroScene animate={!reduced} />
        </div>
      )}
    </div>
  )
}
