import * as calendar from './calendar.js';
export const render = ctx => calendar.render({...ctx, preferencesOnly:true});
export const bind = calendar.bind;
