import { CanvasTexture, LinearFilter } from "three"

/** A soft round sprite so THREE.Points render as discs instead of squares. Browser-only (uses a 2D canvas). */
export function createDiscTexture(): CanvasTexture {
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = 64
  const ctx = canvas.getContext("2d")!
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, "rgba(255,255,255,1)")
  g.addColorStop(0.55, "rgba(255,255,255,1)")
  g.addColorStop(1, "rgba(255,255,255,0)")
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 64, 64)
  const texture = new CanvasTexture(canvas)
  texture.minFilter = LinearFilter
  return texture
}
