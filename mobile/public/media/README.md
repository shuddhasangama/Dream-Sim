# Calendar explainer

`calendar-explainer.mp4` is a 30-second, portrait 1080×1440 H.264 video
with burned-in captions and animated highlights over the current mobile
calendar screenshot. It is intentionally silent and does not autoplay.

Created 2026-09-20 from the local preview calendar. Uses the calendar labels
Matches, Slots, Publish, Sign, Dates and Debrief. Recreate if cadence changes.

The default source in `src/config.js` loads this bundled file. Rebuild the
mobile app in Codemagic to include it; a Railway deployment alone will not
update bundled media. A custom source can be set with DHASHU_CALENDAR_VIDEO_SRC.
