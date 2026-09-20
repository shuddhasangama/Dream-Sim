// Build-time configuration for things whose value is supplied later.
//
// round4-fixes-spec.md §7: the calendar explainer video's FILE is not ready
// yet, so the player and its placement are built now and the source is a
// setting, not a literal in the screen. Set DHASHU_CALENDAR_VIDEO_SRC (and
// optionally DHASHU_CALENDAR_VIDEO_POSTER) at build time to point somewhere
// else; the default is a file bundled from public/media/. A remote URL must
// also be allowed by `media-src` in index.html's CSP.
//
// `import.meta.env` only exists under Vite — guarded so the pure screen
// modules can still be imported by node:test.
const env = (typeof import.meta !== 'undefined' && import.meta.env) || {};

export const CALENDAR_VIDEO = {
  src: env.DHASHU_CALENDAR_VIDEO_SRC || '/media/calendar-explainer.mp4',
  poster: env.DHASHU_CALENDAR_VIDEO_POSTER || '',
};
