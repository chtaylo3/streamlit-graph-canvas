import { useEffect, useRef, useState } from "react";
import { getNodesBounds, getViewportForBounds, type ReactFlowInstance, type Viewport } from "@xyflow/react";
import { absoluteNodes, budgetTransitionOrigin, center, interpolateViewport, prepareTransition, stabilizeContext, translateScene, type Scene } from "./transition";

export function useSceneTransition(target:Scene, options:{
  ready:boolean; maxElements:number; movableContextIds?:ReadonlySet<string>; hasSavedViewport:boolean; revision:string; layoutKey:string; duration:number; anchor?:string|null;
  fitView:"never"|"initial"|"topology-change"; flow:ReactFlowInstance;
  host:HTMLElement; onSettled:(viewport:Viewport)=>void;
}) {
  const [scene,setScene]=useState<Scene>({nodes:[],edges:[]});
  const current=useRef(scene);
  const latest=useRef({target,options}); latest.current={target,options};
  const running=useRef(false), controlViewport=useRef(true);
  const frame=useRef<number|undefined>(undefined);
  const offset=useRef({key:"",x:0,y:0});
  const lastLayout=useRef("");
  const previousAnchor=useRef<string|null|undefined>(undefined);
  const stabilized=useRef<Scene|null>(null);
  const previousMovableIds=useRef<ReadonlySet<string>>(new Set());
  const [reduced,setReduced]=useState(()=>matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(()=>{
    const media=matchMedia("(prefers-reduced-motion: reduce)");
    const update=()=>setReduced(media.matches);
    media.addEventListener("change",update);return ()=>media.removeEventListener("change",update);
  },[]);
  useEffect(()=>{
    if (!options.ready) return;
    const {target,options:settings}=latest.current;
    const layoutChanged=lastLayout.current!==settings.layoutKey;
    const old=absoluteNodes(current.current.nodes);
    const raw=absoluteNodes(target.nodes);
    if (offset.current.key!==settings.layoutKey) {
      const before=old.find(n=>n.id===settings.anchor),after=raw.find(n=>n.id===settings.anchor);
      const a=before&&center(before),b=after&&center(after);
      offset.current={key:settings.layoutKey,x:a&&b?a.x-b.x:0,y:a&&b?a.y-b.y:0};
    }
    const translated=translateScene(target,offset.current);
    // Retain geometry on presentation-only reruns as well.
    const destination=stabilizeContext(layoutChanged?current.current:(stabilized.current??current.current),translated,previousAnchor.current,settings.anchor,new Set([...(settings.movableContextIds??[]),...(layoutChanged?previousMovableIds.current:[])]));
    if(layoutChanged) previousMovableIds.current=settings.movableContextIds??new Set();
    stabilized.current=destination;
    previousAnchor.current=settings.anchor;
    const fromViewport=settings.flow.getViewport();
    let toViewport=fromViewport;
    const first=current.current.nodes.length===0;
    if ((first && (settings.fitView==="topology-change" || (settings.fitView==="initial" && !settings.hasSavedViewport))) || (layoutChanged && settings.fitView==="topology-change")) {
      const element=settings.host.querySelector('.react-flow') as HTMLElement|null;
      const width=element?.clientWidth||settings.host.clientWidth||800;
      const height=element?.clientHeight||settings.host.clientHeight||600;
      const flat=absoluteNodes(destination.nodes);
      if (flat.length) {
        toViewport=getViewportForBounds(getNodesBounds(flat),width,height,0.08,2.5,0.12);

      }
    }
    const duration=reduced||first?0:settings.duration;
    const sample=prepareTransition(budgetTransitionOrigin(current.current,destination,settings.maxElements),destination,settings.anchor);
    const publish=(value:Scene)=>{current.current=value;setScene(value);};
    let active=true;
    controlViewport.current=true;
    running.current=duration>0;
    settings.host.dataset.sgcTransition=duration>0?"running":"idle";
    settings.host.dataset.sgcTransitionDuration=String(duration);
    settings.host.dataset.sgcLayoutPending="false";
    const finish=()=>{
      if (!active) return;
      publish(destination);lastLayout.current=settings.layoutKey;
      // Keep move-end callbacks quiet until the final viewport is applied.
      void (controlViewport.current ? settings.flow.setViewport(toViewport) : Promise.resolve()).then(()=>{
        if (!active) return;
        running.current=false;settings.host.dataset.sgcTransition="idle";
        settings.onSettled(settings.flow.getViewport());
      });
    };
    if (!duration) {finish();return ()=>{active=false;};}
    const start=performance.now();
    publish(sample(0));
    const tick=(now:number)=>{
      if (!active) return;
      const progress=Math.min(1,(now-start)/duration);
      if (progress>=1) {finish();return;}
      publish(sample(progress));
      if (controlViewport.current) void settings.flow.setViewport(interpolateViewport(fromViewport,toViewport,progress));
      frame.current=requestAnimationFrame(tick);
    };
    frame.current=requestAnimationFrame(tick);
    return ()=>{
      active=false;if(frame.current!==undefined) cancelAnimationFrame(frame.current);
      running.current=false;
    };
  },[options.ready,options.revision,options.duration,reduced]);
  useEffect(()=>{
    if (!options.ready) options.host.dataset.sgcLayoutPending="true";
  },[options.ready,options.host]);
  useEffect(()=>()=>{if(frame.current!==undefined) cancelAnimationFrame(frame.current);running.current=false;},[]);
  // Refresh event handlers even while an old scene is retained for layout.
  const live=new Map(target.nodes.map(n=>[n.id,n]));
  const rendered:Scene={...scene,nodes:scene.nodes.map(n=>{
    const next=live.get(n.id);
    if (!next || n.data.__transitionExiting) return {...n,selectable:false,focusable:false,domAttributes:{inert:true,"aria-hidden":true}};
    return {...n,data:{...n.data,onKeyboardActivate:next.data.onKeyboardActivate,onToggleGroup:next.data.onToggleGroup},selected:next.selected};
  })};
  return {scene:rendered,running,interruptViewport:()=>{controlViewport.current=false;}};
}
