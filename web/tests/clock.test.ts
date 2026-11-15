import {test} from 'node:test';
import assert from 'node:assert/strict';
import {interpolate,PlaybackClock} from '../src/clock';
import type {Body} from '../src/types';
const body:Body={id:'prey-0',x:1,y:2,vx:1,vy:0,energy:50,alive:true,death_tick:null,food_eaten:0,objective:'FLEE',target_id:null};
test('interpolation remains between authoritative coordinates and does not mutate input',()=>{const end={...body,x:3,y:4,vx:2,vy:1};const mid=interpolate(body,end,.5);assert.equal(mid.x,2);assert.equal(mid.y,3);assert.equal(body.x,1);assert.equal(mid.energy,50);assert.equal(interpolate(body,end,-1).x,1);assert.equal(interpolate(body,end,2).x,3);});
test('capture applies only at recorded frame boundary',()=>{const dead={...body,x:2,alive:false,death_tick:1};assert.equal(interpolate(body,dead,.99).alive,true);assert.equal(interpolate(body,dead,1).alive,false);assert.equal(interpolate(dead,body,.5).alive,false);});
test('clock preserves pause and speed, bounds seeks and caps frame-drop catchup',()=>{const c=new PlaybackClock();c.playing=true;c.advance(0,100);assert.equal(c.advance(100,100),.8);c.pause();c.advance(10000,100);assert.equal(c.tick,.8);c.speed=2;c.playing=true;c.advance(10100,100);assert.ok(Math.abs(c.tick-2.4)<1e-9);c.advance(20100,100);assert.ok(Math.abs(c.tick-6.4)<1e-9);c.seek(1000,20);assert.equal(c.tick,20);c.seek(-10,20);assert.equal(c.tick,0);c.reset();assert.equal(c.playing,false);});
test('live clock waits at buffer end without inventing future ticks',()=>{const c=new PlaybackClock();c.playing=true;c.advance(0,1);c.advance(250,1);assert.equal(c.tick,1);c.advance(500,1);assert.equal(c.tick,1);c.advance(750,2);assert.equal(c.tick,2);});
