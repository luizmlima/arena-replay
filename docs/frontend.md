# Frontend v0.1

From the repository root, start the existing API: `uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`. In a second terminal: `cd frontend`, `npm install`, `npm test`, `npm run build`, `npm run dev`. Open http://127.0.0.1:5173. Vite proxies `/api` to port 8000; no backend changes or external services are needed. A court-specific URL is `http://127.0.0.1:5173/?court=court01`.

Select an available date and continuous interval. Select a preview position and click to request up to 60 seconds of watermarked video. Select start and end using the sliders or the video playhead, then add the range. Multiple ranges may be selected from different hours/dates of the same court. Selecting another court clears the cart. Full-hour purchase is enabled only when an entire clock hour is available and replaces the selection. Quotes are validated by the existing backend. Payment and original downloads are disabled. Preview generation is on demand and not continuous streaming; no production access, retention or authentication is implemented here. Timestamps use UTC-03 (arena timezone) and are rounded inward to whole seconds. The first npm install creates the lockfile; commit it alongside frontend source. Tests cover timeline helpers without npm dependencies.


## Mobile-first refinement (v0.2)

- Compact header, hero and two-column court selection on screens up to 740px.
- Larger touch targets, responsive time slots, full-width player and controls.
- A fixed mobile selection summary links to the existing cart when it contains clips; the backend remains the source of the price.
- Desktop layout, API contracts, selection logic and pricing remain unchanged.
- Verify at 320, 360, 390, 430 and desktop widths, including a populated cart, playback, selection and removing the last clip.
