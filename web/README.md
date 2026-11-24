# EKA web

Next.js (App Router) + TypeScript frontend for the Enterprise Knowledge Agent backend.

| Concern | Library |
| --- | --- |
| Framework | Next.js 16, React 19, TypeScript (strict) |
| UI | Tailwind CSS v4, shadcn/ui (Base UI primitives), lucide-react, Framer Motion, sonner, cmdk |
| Server state | TanStack Query |
| Client state | Zustand (persisted settings) |
| Forms / validation | React Hook Form, Zod (also validates every backend response) |
| Tests | Vitest, Testing Library, MSW |

## Run

```bash
pnpm install
pnpm dev            # http://localhost:3000, expects the API at http://localhost:8000
```

The backend URL can be changed at runtime on the **Settings** page, or at build time with
`NEXT_PUBLIC_API_URL`.

## Checks

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Layout

```
src/app/            routes (App Router)
src/components/     feature components; ui/ holds the shadcn primitives
src/lib/api/        typed client: zod schemas, fetch wrapper, SSE parser
src/lib/store/      zustand stores
src/test/           MSW server and test utilities
```
