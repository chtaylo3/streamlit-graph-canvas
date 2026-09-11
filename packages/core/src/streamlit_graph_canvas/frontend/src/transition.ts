import type { Node, Edge, XYPosition, Viewport } from "@xyflow/react";

export type Scene = { nodes: Node[]; edges: Edge[] };
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const point = (a: XYPosition, b: XYPosition, t: number) => ({ x: mix(a.x,b.x,t), y: mix(a.y,b.y,t) });
const dimensions = (n: Node) => ({ width: n.width ?? n.measured?.width ?? 180, height: n.height ?? n.measured?.height ?? 92 });
export const center = (n: Node) => ({ x: n.position.x + dimensions(n).width / 2, y: n.position.y + dimensions(n).height / 2 });
export function absoluteNodes(nodes: Node[]): Node[] {
  const byId = new Map(nodes.map(n => [n.id,n]));
  const memo = new Map<string, XYPosition>();
  const position = (n: Node): XYPosition => {
    if (memo.has(n.id)) return memo.get(n.id)!;
    const parent = n.parentId ? byId.get(n.parentId) : undefined;
    const p = parent ? position(parent) : {x:0,y:0};
    const result = { x: p.x+n.position.x, y: p.y+n.position.y };
    memo.set(n.id,result); return result;
  };
  return nodes.map(n => ({...n, parentId:undefined, position:position(n)}));
}
export function translateScene(scene: Scene, offset: XYPosition): Scene {
  return {
    nodes: scene.nodes.map(n => n.parentId ? n : ({...n,position:{x:n.position.x+offset.x,y:n.position.y+offset.y}})),
    edges: scene.edges.map(e => ({...e,data:{...e.data,route:route(e)?.map(p=>({x:p.x+offset.x,y:p.y+offset.y}))}})),
  };
}
/** Retain context outside the active branch when revisiting it or a sibling. */
export function stabilizeContext(previous: Scene, target: Scene, previousAnchor?: string | null, anchor?: string | null, movableIds:ReadonlySet<string> = new Set()): Scene {
  if (!anchor || !previousAnchor) return target;
  const parents = (scene: Scene, id: string) => new Set(scene.edges.filter(e=>e.target===id).map(e=>e.source));
  const oldParents=parents(previous,previousAnchor), newParents=parents(target,anchor);
  if (anchor!==previousAnchor && ![...newParents].some(id=>oldParents.has(id))) return target;
  const descendants=new Set<string>();
  const children=new Map<string,string[]>();
  for (const e of target.edges) children.set(e.source,[...(children.get(e.source)??[]),e.target]);
  for (const n of target.nodes) if(n.parentId) children.set(n.parentId,[...(children.get(n.parentId)??[]),n.id]);
  const queue=[anchor], visited=new Set(queue);
  for (let i=0;i<queue.length;i++) for (const id of children.get(queue[i])??[]) {
    if (!visited.has(id)) {visited.add(id);descendants.add(id);queue.push(id);}
  }
  const old=new Map(absoluteNodes(previous.nodes).filter(n=>!n.data.__transitionExiting).map(n=>[n.id,n]));
  const flat=absoluteNodes(target.nodes);
  const positions=new Map(flat.map(n=>[n.id,!descendants.has(n.id)&&!movableIds.has(n.id)&&old.has(n.id) ? old.get(n.id)!.position : n.position]));
  const nodes=target.nodes.map(n=>{
    const p=positions.get(n.id)!, parent=n.parentId?positions.get(n.parentId):undefined;
    return {...n,position:{x:p.x-(parent?.x??0),y:p.y-(parent?.y??0)}};
  });
  const raw=new Map(flat.map(n=>[n.id,n]));
  const oldEdges=new Map(previous.edges.map(e=>[e.id,e]));
  const unchanged=(id:string)=>{
    const a=old.get(id), b=raw.get(id), p=positions.get(id);
    return a&&b&&p&&a.position.x===p.x&&a.position.y===p.y&&dimensions(a).width===dimensions(b).width&&dimensions(a).height===dimensions(b).height;
  };
  return {nodes,edges:target.edges.map(e=>{
    const prior=oldEdges.get(e.id);
    if (prior && prior.source===e.source && prior.target===e.target && prior.sourceHandle===e.sourceHandle && prior.targetHandle===e.targetHandle && unchanged(e.source)&&unchanged(e.target)) {
      return {...e,data:{...e.data,route:route(prior)}};
    }
    // Routes computed before pinning cannot serve endpoints that moved.
    // Use the normal handle-aware renderer for those boundary connections.
    const moved=[e.source,e.target].some(id=>{
      const p=positions.get(id), n=raw.get(id);return p&&n&&(p.x!==n.position.x||p.y!==n.position.y);
    });
    return moved?{...e,data:{...e.data,route:undefined}}:e;
  })};
}
function route(e: Edge): XYPosition[] | undefined { return e.data?.route as XYPosition[] | undefined; }
function opacity(item: Node | Edge) { return Number(item.style?.opacity ?? 1); }
/** Arc-length resampling gives matching vertices when orthogonal paths differ. */
export function resample(points: XYPosition[], count: number): XYPosition[] {
  if (!points.length) return [];
  const lengths = [0];
  for (let i=1;i<points.length;i++) lengths.push(lengths[i-1]+Math.hypot(points[i].x-points[i-1].x,points[i].y-points[i-1].y));
  const total=lengths.at(-1)!;
  let segment=1;
  return Array.from({length:count},(_,i)=>{
    const distance=total*i/Math.max(1,count-1);
    while(segment<points.length-1 && lengths[segment]<distance) segment++;
    if (!total || points.length===1) return {...points[0]};
    const span=lengths[segment]-lengths[segment-1];
    return point(points[segment-1],points[segment],span ? (distance-lengths[segment-1])/span : 0);
  });
}
/** Retire outgoing items immediately when retaining them would exceed the display budget. */
export function budgetTransitionOrigin(previous: Scene, target: Scene, limit: number): Scene {
  const nodeIds=new Set(target.nodes.map(n=>n.id)), edgeIds=new Set(target.edges.map(e=>e.id));
  const combined=target.nodes.length+target.edges.length+previous.nodes.filter(n=>!nodeIds.has(n.id)).length+previous.edges.filter(e=>!edgeIds.has(e.id)).length;
  if (combined<=limit) return previous;
  return {nodes:absoluteNodes(previous.nodes).filter(n=>nodeIds.has(n.id)),edges:previous.edges.filter(e=>edgeIds.has(e.id))};
}
export function prepareTransition(previous: Scene, target: Scene, anchorId?: string | null) {
  const targetIds=new Set(target.nodes.map(n=>n.id));
  // Do not accumulate outgoing ghosts across interrupted navigations.
  const fromNodes=absoluteNodes(previous.nodes.filter(n=>!n.data.__transitionExiting || targetIds.has(n.id)));
  const toNodes=absoluteNodes(target.nodes);
  const from=new Map(fromNodes.map(n=>[n.id,n])), to=new Map(toNodes.map(n=>[n.id,n]));
  const anchor=anchorId ? from.get(anchorId) ?? to.get(anchorId) : undefined;
  const pairs=toNodes.map(n=>{
    const old=from.get(n.id);
    const parent=target.nodes.find(t=>t.id===n.id)?.parentId;
    const origin=old ?? (parent ? from.get(parent) : undefined) ?? anchor;
    return { from:old ?? {...n,position:origin ? {x:center(origin).x-dimensions(n).width/2,y:center(origin).y-dimensions(n).height/2} : n.position,style:{...n.style,opacity:0}}, to:n, exiting:false };
  });
  for (const n of fromNodes) if (!to.has(n.id)) pairs.push({from:n,to:{...n,style:{...n.style,opacity:0}},exiting:true});
  const oldEdges=new Map(previous.edges.filter(e=>from.has(e.source)&&from.has(e.target)).map(e=>[e.id,e]));
  const edgePairs=target.edges.map(e=>{
    const old=oldEdges.get(e.id);
    let start=old && route(old), end=route(e);
    if (!start && end) {
      const source=pairs.find(n=>n.to.id===e.source), dest=pairs.find(n=>n.to.id===e.target);
      const delta=(n: typeof source)=>n ? {x:n.from.position.x-n.to.position.x,y:n.from.position.y-n.to.position.y} : {x:0,y:0};
      const a=delta(source), b=delta(dest);
      start=end.map((p,i)=>{const d=point(a,b,i/Math.max(1,end!.length-1));return {x:p.x+d.x,y:p.y+d.y};});
    }
    if (start && !end) {
      const source=pairs.find(n=>n.to.id===e.source), dest=pairs.find(n=>n.to.id===e.target);
      const delta=(n: typeof source)=>n ? {x:n.to.position.x-n.from.position.x,y:n.to.position.y-n.from.position.y} : {x:0,y:0};
      const a=delta(source),b=delta(dest);
      end=start.map((p,i)=>{const d=point(a,b,i/Math.max(1,start!.length-1));return {x:p.x+d.x,y:p.y+d.y};});
    }
    const same=start&&end&&start.length===end.length&&start.every((p,i)=>p.x===end![i].x&&p.y===end![i].y);
    const count=Math.min(64,Math.max(start?.length??0,end?.length??0,2));
    return {from:old ?? {...e,style:{...e.style,opacity:0}},to:e,start:same?start:start?resample(start,count):undefined,end:same?end:end?resample(end,count):undefined};
  });
  const newEdges=new Set(target.edges.map(e=>e.id));
  for (const e of oldEdges.values()) if (!newEdges.has(e.id)) edgePairs.push({from:e,to:{...e,style:{...e.style,opacity:0}},start:route(e),end:route(e)});
  return (progress:number):Scene => {
    if (progress>=1) return target;
    const t=progress*progress*(3-2*progress);
    return {
      nodes:pairs.map(({from:a,to:b,exiting})=>{
        const sizeA=dimensions(a),sizeB=dimensions(b);
        const width=mix(sizeA.width,sizeB.width,t),height=mix(sizeA.height,sizeB.height,t);
        return {...b,position:point(a.position,b.position,t),width,height,measured:{width,height},
          data:{...b.data,__transitionExiting:exiting},
          ...(exiting ? {selectable:false,focusable:false,domAttributes:{inert:true,"aria-hidden":true}} : {}),
          style:{...b.style,width,height,opacity:mix(opacity(a),opacity(b),t),...(exiting?{pointerEvents:"none"}: {})}};
      }),
      edges:edgePairs.map(({from:a,to:b,start,end})=>({...b,selectable:false,style:{...b.style,opacity:mix(opacity(a),opacity(b),t)},
        data:{...b.data,route:start&&end?start.map((p,i)=>point(p,end![i]??p,t)):undefined}})),
    };
  };
}
export function interpolateViewport(a:Viewport,b:Viewport,t:number):Viewport {
  const eased=t*t*(3-2*t);return {...point(a,b,eased),zoom:mix(a.zoom,b.zoom,eased)};
}
