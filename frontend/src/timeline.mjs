// Arena timezone: America/Fortaleza (UTC-03:00 for the dates supported here).
const local = (ms) => new Date(ms - 3 * 3600000).toISOString();
export const dateKey = (ms) => local(ms).slice(0,10);
export const clock = (ms) => local(ms).slice(11,19);
export const iso = (ms) => new Date(ms).toISOString();
export function windows(segments) {
  const merged=[];
  const sorted=segments.map(s=>({start:Date.parse(s.start),end:Date.parse(s.end)})).filter(s=>Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.end>s.start).sort((a,b)=>a.start-b.start);
  for(const s of sorted){const last=merged.at(-1);if(last&&s.start<=last.end)last.end=Math.max(last.end,s.end);else merged.push({...s});}
  const out=[];
  for(const s of merged){let cursor=s.start;while(cursor<s.end){const boundary=(Math.floor(cursor/3600000)+1)*3600000;const stop=Math.min(boundary,s.end);const start=Math.ceil(cursor/1000)*1000;const end=Math.floor(stop/1000)*1000;if(end-start>=1000)out.push({start,end,day:dateKey(start),hour:clock(Math.floor(start/3600000)*3600000).slice(0,5)});cursor=stop;}}
  return out;
}
export const overlaps=(a,b)=>a.start<b.end&&b.start<a.end;
export const lengthSeconds=(ranges)=>ranges.reduce((total,r)=>total+(r.end-r.start)/1000,0);
export const requestRanges=(ranges)=>ranges.map(r=>({start:iso(r.start),end:iso(r.end)}));
