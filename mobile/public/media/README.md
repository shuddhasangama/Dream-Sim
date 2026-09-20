Drop the calendar explainer video here as `calendar-explainer.mp4` (H.264/AAC,
short, captions burned in or a .vtt alongside). Until it exists the Week screen
shows a "video coming soon" placeholder instead of a broken player.

To serve it from somewhere else, set `DHASHU_CALENDAR_VIDEO_SRC` (and optionally
`DHASHU_CALENDAR_VIDEO_POSTER`) at build time — see `src/config.js`. A remote URL
must also be allowed by `media-src` in the CSP in `index.html`.
