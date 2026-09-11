import { describe, expect, it } from "vitest";
import type { Node } from "@xyflow/react";
import { absoluteNodes, budgetTransitionOrigin, stabilizeContext, prepareTransition, resample, translateScene, interpolateViewport, type Scene } from "./transition";
const node=(id:string,x=0,parentId?:string):Node=>({id,position:{x,y:0},width:100,height:80,data:{},parentId});
const scene=(nodes:Node[]):Scene=>({nodes,edges:[]});

describe("coordinated scene transitions",()=>{
  it("moves shared nodes, fades additions and retires outgoing nodes",()=>{
    const target=scene([node("shared",100),node("new",200)]);
    const sample=prepareTransition(scene([node("shared"),node("old")]),target,"shared");
    const middle=sample(.5);
    expect(middle.nodes.find(n=>n.id==="shared")!.position.x).toBe(50);
    expect(middle.nodes.find(n=>n.id==="new")!.style!.opacity).toBe(.5);
    const old=middle.nodes.find(n=>n.id==="old")!;
    expect(old.domAttributes?.inert).toBe(true);
    expect(old.style!.opacity).toBe(.5);
    expect(sample(1)).toBe(target);
  });
  it("preserves world coordinates when children change containers",()=>{
    const before=scene([node("group",100),node("child",10,"group")]);
    const after=scene([node("group2",300),node("child",20,"group2")]);
    const sample=prepareTransition(before,after);
    expect(sample(0).nodes.find(n=>n.id==="child")!.position.x).toBe(110);
    expect(sample(.5).nodes.find(n=>n.id==="child")!.position.x).toBe(215);
    expect(sample(1).nodes.find(n=>n.id==="child")!.parentId).toBe("group2");
    const shifted=translateScene(after,{x:10,y:20});
    expect(absoluteNodes(shifted.nodes).find(n=>n.id==="child")!.position).toEqual({x:330,y:20});
  });
  it("restarts from the displayed frame and bounds outgoing ghosts",()=>{
    const middle=prepareTransition(scene([node("a"),node("old")]),scene([node("a",100),node("b")]))(.4);
    const next=prepareTransition(middle,scene([node("a",200),node("c")]));
    expect(next(0).nodes.find(n=>n.id==="a")!.position).toEqual(middle.nodes.find(n=>n.id==="a")!.position);
    expect(next(0).nodes.map(n=>n.id)).not.toContain("old");
    expect(next(1).nodes.map(n=>n.id)).toEqual(["a","c"]);
  });
  it("morphs routed edges with different bend counts without nonfinite points",()=>{
    const a:Scene={nodes:[node("a"),node("b",100)],edges:[{id:"e",source:"a",target:"b",data:{route:[{x:0,y:0},{x:100,y:0}]}}]};
    const b:Scene={nodes:[node("a",20),node("b",200)],edges:[{id:"e",source:"a",target:"b",data:{route:[{x:20,y:0},{x:20,y:40},{x:200,y:40},{x:200,y:0}]}}]};
    const middle=prepareTransition(a,b)(.5);
    const points=middle.edges[0].data!.route as {x:number;y:number}[];
    expect(points[0]).toEqual({x:10,y:0});expect(points.at(-1)).toEqual({x:150,y:0});
    expect(points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y))).toBe(true);
    expect(resample([{x:2,y:3},{x:2,y:3}],4)).toEqual(Array(4).fill({x:2,y:3}));
  });
  it("handles a large scene and drops all ghosts at completion",()=>{
    const before=scene(Array.from({length:500},(_,i)=>node(String(i),i*110)));
    const after=scene(Array.from({length:500},(_,i)=>node(String(i+250),i*110)));
    const sample=prepareTransition(before,after);
    expect(sample(.5).nodes).toHaveLength(750);
    expect(sample(1).nodes).toHaveLength(500);
    expect(interpolateViewport({x:0,y:0,zoom:1},{x:100,y:50,zoom:.5},.5)).toEqual({x:50,y:25,zoom:.75});
  });
});


describe("sibling context stability",()=>{
  const edge=(source:string,target:string)=>({id:source+target,source,target,data:{route:[{x:10,y:10},{x:10,y:30},{x:130,y:30}]}});
  it("pins ancestors and peers and preserves their exact bends throughout sideways motion",()=>{
    const old:Scene={nodes:[node("root"),node("repo",100),node("a",200),node("b",300)],edges:[edge("root","repo"),edge("repo","a"),edge("repo","b")]};
    const next:Scene={nodes:[node("root",50),node("repo",150),node("a",190),node("b",300),node("child",400)],edges:[...old.edges.map(e=>({...e,data:{route:[{x:40,y:10},{x:40,y:50},{x:100,y:50}]}})),edge("b","child")]};
    const pinned=stabilizeContext(old,next,"a","b");
    for(const n of old.nodes) expect(pinned.nodes.find(t=>t.id===n.id)!.position).toEqual(n.position);
    expect(pinned.nodes.at(-1)!.position.x).toBe(400);
    const sample=prepareTransition(old,pinned,"b");
    for(const t of [0,.25,.5,.9,1]) {
      expect(sample(t).edges[0].data!.route).toEqual(old.edges[0].data!.route);
      expect(sample(t).nodes[0].position).toEqual(old.nodes[0].position);
    }
    const again=stabilizeContext(pinned,next,"b","b");
    expect(again.nodes[0].position).toEqual(old.nodes[0].position);
  });
  it("does not pin across unrelated parents or without an anchor",()=>{
    const before:Scene={nodes:[node("a"),node("b")],edges:[edge("x","a")]};
    const target:Scene={nodes:[node("a",100),node("b",200)],edges:[edge("y","b")]};
    expect(stabilizeContext(before,target,"a","b")).toBe(target);
    expect(stabilizeContext(before,target)).toBe(target);
  });
});


it("retires outgoing geometry when old and new scenes would exceed the display budget",()=>{
  const previous=scene([node("shared"),node("outgoing")]);
  const target=scene([node("shared",100),node("incoming")]);
  expect(budgetTransitionOrigin(previous,target,3)).toBe(previous);
  const origin=budgetTransitionOrigin(previous,target,2);
  expect(origin.nodes.map(n=>n.id)).toEqual(["shared"]);
  expect(prepareTransition(origin,target)(.5).nodes).toHaveLength(2);
});
