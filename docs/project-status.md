# Arena Replay — Project Status

Last updated: 2026-11-26

## Product requirements

- Beach tennis replay platform.
- Four outdoor courts with one IP PoE camera each.
- Self-hosted server inside the arena.
- Dell Latitude 5490 as reference hardware.
- 2 TB external storage.
- Recording schedule: 18:00 to 00:00.
- Original recording retention: 7 days.
- Public previews without mandatory registration.
- Remote access through Wi-Fi, 4G and 5G.
- Individual QR code for each court.
- Manual selection of multiple video clips.
- Individual and combined video exports.
- Full-hour purchases.
- Mobile-first user experience.
- No paid software licenses.

## Provisional commercial rules

- BRL 5 per minute.
- BRL 50 per full hour.
- Minimum order of BRL 5.
- Pricing must be reviewed later.
- Pix integration postponed.

## Completed

- Development environment.
- GitHub repository.
- FFmpeg video processing engine.
- Clip extraction and compilation.
- Watermarked video previews.
- MediaMTX RTSP server.
- Four-camera simulator.
- Continuous multi-camera recording.
- Timestamp-based recording catalog.
- Cross-segment video exports.
- Midnight timestamp handling.
- Initial FastAPI backend.
- React and TypeScript frontend.
- Mobile-first frontend update.
- Clip selection and price calculation.
- 42 passing backend tests.

## Next development session

1. Refine the mobile video selection experience.
2. Implement persistent orders and database.
3. Complete full-hour purchase flow.
4. Implement simulated payment.
5. Implement purchased video delivery.
6. Implement recording schedule.
7. Implement seven-day retention.
8. Develop administration dashboard.
9. Integrate Pix.
10. Implement production security and remote access.
11. Validate with physical cameras.

## Known limitations

- Recording timestamps are approximate.
- Previews are limited to 60 seconds per request.
- No real payment integration.
- No production access controls.
- Automatic retention is not implemented.
- Physical camera performance is not validated.
- Commercial image rights and privacy requirements
  must be addressed before public deployment.

## Development cost

Software and external development services: BRL 0.
