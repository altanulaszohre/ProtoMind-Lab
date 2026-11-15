import 'pixi.js/unsafe-eval';
import {Application,Assets,Container,Graphics,MeshPlane,Rectangle,Sprite,Texture} from 'pixi.js';
import {interpolate} from './clock';
import type {Body,Frame,Config} from './types';

export class Ecosystem {
  app=new Application(); fish=new Map<string,{root:Container;mesh:MeshPlane;original:Float32Array}>();
  resources=new Map<string,Sprite>(); overlays=new Graphics(); water=new Graphics(); world=new Container();
  prey!:Texture; predator!:Texture; food!:Texture; selected='prey-0'; perception=false; labels=false; trails=true; pressure=false; groups=false;
  points=new Map<string,{x:number;y:number}>(); frameTimes:number[]=[]; fps=0; renderMs=0;
  private last=0; private offsetX=0; private offsetY=0; private scale=1;
  async init(host:HTMLElement,select:(id:string)=>void) {
    await this.app.init({resizeTo:host,backgroundAlpha:0,antialias:true,resolution:Math.min(devicePixelRatio,2),autoDensity:true,preference:'webgl',autoStart:false});
    host.appendChild(this.app.canvas); this.app.canvas.setAttribute('aria-label','Interactive experimental arena. Select an agent or use the agent selector.');
    const atlas=await Assets.load<Texture>('/assets/synthetic-atlas.png');
    const w=atlas.width,h=atlas.height;
    this.prey=new Texture({source:atlas.source,frame:new Rectangle(60,60,880,440)});
    this.predator=new Texture({source:atlas.source,frame:new Rectangle(140,550,740,390)});
    this.food=new Texture({source:atlas.source,frame:new Rectangle(210,1020,600,450)});
    this.app.stage.addChild(this.water,this.world,this.overlays);
    this.app.canvas.addEventListener('pointerdown',e=>{
      const rect=this.app.canvas.getBoundingClientRect(); const x=e.clientX-rect.left,y=e.clientY-rect.top;
      let best='',dist=30;
      for(const [id,p] of this.points){const d=Math.hypot(x-p.x,y-p.y);if(d<dist){best=id;dist=d;}}
      if(best) select(best);
    });
  }
  render(a:Frame,b:Frame|undefined,alpha:number,config:Config,tick:number,now:number,history:Frame[]=[]) {
    const start=performance.now(); const width=this.app.screen.width,height=this.app.screen.height;
    this.scale=Math.min((width-70)/config.width,(height-100)/config.height);
    this.offsetX=(width-config.width*this.scale)/2; this.offsetY=(height-config.height*this.scale)/2;
    const s=this.scale,ox=this.offsetX,oy=this.offsetY;
    this.overlays.clear(); this.water.clear(); this.points.clear();
    this.overlays.rect(ox,oy,config.width*s,config.height*s).stroke({color:0x7294c5,alpha:.13,width:1});
    if(this.pressure && a.predator){this.water.circle(ox+a.predator.x*s,oy+a.predator.y*s,config.predator_perception*s).fill({color:0xf16c45,alpha:.035}).stroke({color:0xf16c45,alpha:.17,width:1});}
    if(this.groups){const alive=a.prey.filter(p=>p.alive);for(let i=0;i<alive.length;i++)for(let j=i+1;j<alive.length;j++){const p=alive[i],q=alive[j];if(Math.hypot(p.x-q.x,p.y-q.y)<=config.perception)this.water.moveTo(ox+p.x*s,oy+p.y*s).lineTo(ox+q.x*s,oy+q.y*s).stroke({color:0x2857f0,alpha:.09,width:1});}}
    if(this.trails){const previous=history.slice(Math.max(0,a.tick-14),a.tick+1);for(const p of [...a.prey,...(a.predator?[a.predator]:[])]){if(!p.alive)continue;previous.forEach((f,i)=>{const point=p.id.startsWith('predator')?f.predator:f.prey.find(b=>b.id===p.id);if(point){if(i===0)this.water.moveTo(ox+point.x*s,oy+point.y*s);else this.water.lineTo(ox+point.x*s,oy+point.y*s);}});this.water.stroke({color:p.id.startsWith('predator')?0xf16c45:0x3b7ced,alpha:.28,width:1.1});}}
    const all=[...a.prey,...(a.predator?[a.predator]:[])];
    const visible=new Set<string>();
    for(const body of all) {
      if(!body.alive) continue;
      const next=body.id.startsWith('predator')?b?.predator??undefined:b?.prey.find(p=>p.id===body.id);
      const p=interpolate(body,next,alpha);
      if(!p.alive) continue;
      visible.add(p.id);
      let fish=this.fish.get(p.id);
      const predator=p.id.startsWith('predator');
      if(!fish) {
        const mesh=new MeshPlane({texture:predator?this.predator:this.prey,verticesX:14,verticesY:3});
        const root=new Container(); root.addChild(mesh); this.world.addChild(root);
        mesh.pivot.set(mesh.texture.width/2,mesh.texture.height/2);
        fish={root,mesh,original:new Float32Array(mesh.geometry.positions)};this.fish.set(p.id,fish);
      }
      fish.root.visible=true;
      const x=ox+p.x*s,y=oy+p.y*s;
      const speed=Math.hypot(p.vx,p.vy),max=predator?config.predator_speed:config.prey_speed;
      const acceleration=next?Math.hypot(next.vx-body.vx,next.vy-body.vy):0;
      fish.root.position.set(x,y);
      const angle=speed>1e-8?Math.atan2(p.vy,p.vx):0;
      fish.root.rotation=angle;
      const length=predator?Math.max(49,Math.min(66,s*13)):Math.max(33,Math.min(48,s*10));
      fish.root.scale.set(length/fish.mesh.texture.width,(Math.cos(angle)<0?-1:1)*length/fish.mesh.texture.width);
      const verts=fish.mesh.geometry.positions; const tw=fish.mesh.texture.width;
      const phase=tick*(1.8+speed/max*3.5)+Number(p.id.split('-')[1])*2.399;
      for(let i=0;i<verts.length;i+=2) {
        const u=fish.original[i]/tw; const tail=(1-u)**2;
        verts[i]=fish.original[i];
        verts[i+1]=fish.original[i+1]+Math.sin(phase-u*5)*tail*tw*(.002+.012*speed/max+.006*acceleration);
      }
      fish.mesh.geometry.getBuffer('aPosition').update();
      this.points.set(p.id,{x,y});
      if(p.id===this.selected) {
        this.overlays.circle(x,y,predator?48:27).stroke({color:0x2857f0,alpha:.8,width:1});
        this.overlays.circle(x,y,3).stroke({color:0x2857f0,alpha:.55,width:1});
        if(this.perception) this.overlays.circle(x,y,(predator?config.predator_perception:config.perception)*s).fill({color:0x2857f0,alpha:.025}).stroke({color:0x2857f0,alpha:.24,width:1});
      }
      // Capture marker is shown only on the actual engine event frame, at its recorded location.
      if(predator && a.events.some(e=>e.type==='predation')) this.overlays.circle(x,y,35+alpha*16).stroke({color:0xf16c45,alpha:.8*(1-alpha),width:2});
    }
    for(const [id,fish] of this.fish){if(!all.some(b=>b.id===id)){fish.root.destroy({children:true});this.fish.delete(id);}else fish.root.visible=visible.has(id);}
    const foodIds=new Set(a.food.map(f=>f.id));
    for(const f of a.food){
      let sprite=this.resources.get(f.id);
      if(!sprite){sprite=new Sprite(this.food);sprite.anchor.set(.5);this.resources.set(f.id,sprite);this.world.addChildAt(sprite,0);}
      sprite.position.set(ox+f.x*s,oy+f.y*s);sprite.width=23;sprite.height=17;sprite.alpha=.9;
    }
    for(const [id,sprite] of this.resources) if(!foodIds.has(id)){sprite.destroy();this.resources.delete(id);}
    this.app.render();
    this.renderMs=performance.now()-start;
    if(this.last && now-this.last<1000) this.frameTimes.push(now-this.last);
    if(this.frameTimes.length>120)this.frameTimes.shift();
    this.fps=this.frameTimes.length?1000/(this.frameTimes.reduce((v,n)=>v+n,0)/this.frameTimes.length):0;this.last=now;
  }
}
