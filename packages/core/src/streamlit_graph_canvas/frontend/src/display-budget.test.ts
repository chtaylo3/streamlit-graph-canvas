import { describe, expect, it } from "vitest";
import { planChildGroups, type GroupTopologyNode, type GroupTopologyEdge, type ChildGroupSpec } from "./child-groups";
import { applyDisplayBudget } from "./display-budget";
const spec: ChildGroupSpec={edgeType:"direct",label:"Direct dependencies",threshold:1,display:"collection",direction:"right",collapsed:true};
const make=(count:number)=>({
  nodes:[{id:"account",type:"context"},{id:"repo",type:"context"},{id:"manifest",type:"manifest"},...Array.from({length:count},(_,i)=>({id:`d${i}`,type:"dependency"}))],
  edges:[{id:"owns",source:"account",target:"repo",type:"owns"},{id:"contains",source:"repo",target:"manifest",type:"contains"},...Array.from({length:count},(_,i)=>({id:`direct${i}`,source:"manifest",target:`d${i}`,type:"direct"}))],
});
function resolve(nodes:GroupTopologyNode[],edges:GroupTopologyEdge[],limit:number,expanded=false,tree=false) {
  const initial=planChildGroups(nodes,edges,tree?{}:{manifest:[{...spec,collapsed:!expanded}]},new Set());
  const plan=applyDisplayBudget(nodes,edges,initial,limit,"manifest");
  const drawnNodes=nodes.filter(n=>!plan.hiddenNodeIds.has(n.id));
  const drawnEdges=edges.filter(e=>!plan.hiddenEdgeIds.has(e.id)&&!plan.hiddenNodeIds.has(e.source)&&!plan.hiddenNodeIds.has(e.target));
  expect(drawnNodes.length+drawnEdges.length+plan.groups.length*2).toBe(plan.renderedElements);
  expect(plan.renderedElements).toBeLessThanOrEqual(limit);
  return plan;
}
describe("rendered collection budget",()=>{
  it("loads all 1,151 members and charges only the collection and drawn elements",()=>{
    const {nodes,edges}=make(1151);
    const collapsed=resolve(nodes,edges,2000);
    expect(collapsed.renderedElements).toBe(7);
    expect(collapsed.groups[0].memberIds).toHaveLength(1151);
    expect(collapsed.omittedNodes).toBe(0);
    const expanded=resolve(nodes,edges,2000,true);
    expect(expanded.renderedElements).toBe(1158);
    expect(expanded.groups[0].renderedMemberCount).toBe(1151);
    expect(expanded.omittedNodes).toBe(0);
  });
  it("limits members while preserving full counts and counts internal edges",()=>{
    const {nodes,edges}=make(10);
    edges.push(...Array.from({length:9},(_,i)=>({id:`link${i}`,source:`d${i}`,target:`d${i+1}`,type:"requires"})));
    const plan=resolve(nodes,edges,10,true);
    expect(plan.renderedElements).toBe(10);
    expect(plan.groups[0].memberIds).toHaveLength(10);
    expect(plan.groups[0].renderedMemberCount).toBe(2);
    expect(plan.omittedNodes).toBe(8);
    expect(resolve(nodes,edges,10).omittedNodes).toBe(0);
  });
  it("charges individual links in tree mode and keeps focus and ancestors",()=>{
    const {nodes,edges}=make(1151);
    const plan=resolve(nodes,edges,2000,true,true);
    expect(plan.renderedElements).toBe(1999);
    expect(plan.omittedNodes).toBe(154);
    for(const id of ["account","repo","manifest"])expect(plan.hiddenNodeIds.has(id)).toBe(false);
  });
  it("counts self-loops and parallel edges separately",()=>{
    const {nodes,edges}=make(1);
    edges.push({id:"self",source:"d0",target:"d0",type:"requires"},{id:"parallel",source:"manifest",target:"d0",type:"requires"});
    const plan=resolve(nodes,edges,9,true);
    expect(plan.renderedElements).toBe(7);
    expect(plan.groups[0].renderedMemberCount).toBe(0);
    expect(resolve(nodes,edges,10,true).renderedElements).toBe(10);
  });
  it("handles a budget too small for a collection without exceeding it",()=>{
    const {nodes,edges}=make(3);
    const plan=resolve(nodes,edges,1,true);
    expect(plan.hiddenNodeIds.has("manifest")).toBe(false);
    expect(plan.groups).toHaveLength(0);
    expect(plan.omittedCollections).toBe(1);
  });
});


it("spends spare capacity on sibling context after the focused collection",()=>{
  const {nodes,edges}=make(3);
  nodes.push({id:"sibling",type:"manifest"});
  edges.push({id:"sibling-edge",source:"repo",target:"sibling",type:"contains"});
  const plan=resolve(nodes,edges,10,true);
  expect(plan.groups[0].renderedMemberCount).toBe(3);
  expect(plan.hiddenNodeIds.has("sibling")).toBe(true);
});


it("counts a shared member once and retains its drawn category edges",()=>{
  const {nodes,edges}=make(1);
  edges.push({id:"resolved",source:"manifest",target:"d0",type:"resolved"});
  const initial=planChildGroups(nodes,edges,{manifest:[{...spec,collapsed:false},{...spec,edgeType:"resolved",collapsed:false}]},new Set());
  const plan=applyDisplayBudget(nodes,edges,initial,12,"manifest");
  expect(plan.renderedElements).toBe(12); // four real nodes, two containers, six edges
  expect(plan.containerOf.has("d0")).toBe(false);
  expect(plan.groups.map(g=>g.renderedMemberCount)).toEqual([1,1]);
  expect(plan.hiddenEdgeIds.has("direct0")).toBe(false);
  expect(plan.hiddenEdgeIds.has("resolved")).toBe(false);
});
