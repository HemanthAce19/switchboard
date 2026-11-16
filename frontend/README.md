# Switchboard front end

Next.js (App Router), React and TypeScript in strict mode, styled with one plain CSS file.
The only runtime dependency besides Next and React is `react-markdown`.
The API contract lives in `../SPEC.md`.

## Run against the back end

```
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, default http://localhost:8000
npm run dev                  # http://localhost:3000
```

The back end must allow the front end's origin (`CORS_ORIGINS=http://localhost:3000`).

## Run against the mock

No Python or API key needed. The mock implements the contract with one scripted run.

```
npm run mock                 # mock back end on :8000 (PORT=... to change)
npm run dev
```

It seeds three runs you can open directly, which is also how the screenshots were taken:

- `/?run=00000000000000000000000000000001` finished run with a critic revision
- `/?run=00000000000000000000000000000002` one task fails and its dependants are skipped
- `/?run=00000000000000000000000000000003` starts playing live when first opened

`/?run=<id>` works for any run, so links are shareable.

## Test and build

```
npm run typecheck
npm test                     # reducer and graph layout unit tests (vitest)
npm run build
```

## Docker

`NEXT_PUBLIC_API_URL` is compiled into the browser bundle, so pass it at build time:

```
docker build --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 -t switchboard-frontend .
docker run -p 3000:3000 switchboard-frontend
```

## How it fits together

- `lib/types.ts` the contract's shapes; `RunEvent` is a discriminated union on `type`.
- `lib/reducer.ts` pure `(state, event) => state`. The whole run view is rebuilt from events.
- `lib/useRunStream.ts` opens the SSE stream with `EventSource` and feeds the reducer.
- `lib/layout.ts` layered DAG layout: a task's layer is its longest path from a root.
- `components/TaskGraph.tsx` SVG edges plus one real `<button>` per task, placed by the layout.
- `mock/server.mjs` development-only stand-in for the back end.
