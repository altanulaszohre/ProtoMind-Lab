export type Config = Record<string, number | boolean | null> & {width:number;height:number;prey_count:number;max_ticks:number;seed:number;perception:number;predator_perception:number;predator_enabled:boolean;prey_speed:number;predator_speed:number;max_energy:number};
export interface Observation {tick:number; id:string; energy:number; neighbors:{id:string;dx:number;dy:number}[]; food:{id:string;dx:number;dy:number}[]; predator:{id:string;dx:number;dy:number}|null}
export interface Body {id:string;x:number;y:number;vx:number;vy:number;energy:number;alive:boolean;death_tick:number|null;food_eaten:number;objective:string;target_id:string|null;observation?:Observation|null;memories?:{tick:number;kind:string;payload:unknown}[];visible_prey?:string[]}
export interface Decision {tick:number;agent:string;raw:string;decision:{objective:string;duration:number;target_id:string|null};valid:boolean;latency_ms:number;tokens:number;trigger:string}
export interface Event {tick:number;type:string;agent:string|null;resource?:string}
export interface Frame {tick:number;prey:Body[];predator:Body|null;food:{id:string;x:number;y:number}[];events:Event[];decisions:Decision[];metrics:Record<string,number>}
export interface Recording {schema:number;id:string;scenario:string;condition:string;mechanism:string;model:unknown;config:Config;status:string;frames:Frame[];error?:string;interpretation:string}
export interface Model {file:string;bytes?:number;has_chat_template?:boolean;estimated_memory_gib?:number;error?:string;[key:string]:unknown}
