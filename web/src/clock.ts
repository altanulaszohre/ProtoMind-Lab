import type {Body} from './types';
export function interpolate(a:Body,b:Body|undefined,alpha:number):Body {
  if(!b || !a.alive) return {...a};
  const t=Math.max(0,Math.min(1,alpha));
  if(t===1) return {...b};
  return {...a,x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,vx:a.vx+(b.vx-a.vx)*t,vy:a.vy+(b.vy-a.vy)*t};
}
export class PlaybackClock {
  tick=0; speed=1; playing=false; private last:number|null=null;
  advance(now:number,maxTick:number) {
    if(this.last!==null && this.playing) this.tick=Math.min(maxTick,this.tick+Math.min(Math.max(0,now-this.last),250)/1000*8*this.speed);
    this.last=now; return this.tick;
  }
  seek(tick:number,maxTick:number) {this.tick=Math.max(0,Math.min(maxTick,tick));this.last=null;}
  pause(){this.playing=false;this.last=null;}
  reset(){this.tick=0;this.last=null;this.playing=false;}
}
