import { describe,it,expect } from "vitest";
import { NAME_FIELD,searchNodes,searchOrder, type SearchQuery, type SearchField } from "./search-model";
const fields:SearchField[]=[NAME_FIELD,{key:"children",label:"Dependencies",kind:"number"},{key:"critical",label:"Critical below",kind:"number"},{key:"ecosystem",label:"Ecosystem",kind:"choice",choices:["PyPI","npm"]}];
const nodes=[{id:"a",label:"Requests",data:{children:3,critical:8,ecosystem:"PyPI"}},{id:"b",label:"urllib3",data:{children:0,critical:0,ecosystem:"PyPI"}},{id:"c",label:"requests-context",data:{children:10,critical:12}},{id:"d",label:"[unknown]",data:{children:null}}];
const query=(change:Partial<SearchQuery>):SearchQuery=>({query:"",criteria:[],matchMode:"all",includeContext:false,...change});
const ids=(q:SearchQuery)=>searchNodes(nodes,fields,q,new Set(["a","b","d"])).matches.map(n=>n.id);
describe("local metadata search",()=>{
  it("matches comma-separated names literally and excludes context by explicit identity",()=>{
    expect(ids(query({query:"REQUESTS, urllib"}))).toEqual(["a","b"]);
    expect(ids(query({query:"requests",includeContext:true}))).toEqual(["a","c"]);
    expect(ids(query({query:"["}))).toEqual(["d"]);
  });
  it("combines numeric criteria without treating missing data as zero",()=>{
    const criteria=[{field:"children",operator:"gte",value:1},{field:"critical",operator:"gt",value:7}];
    expect(ids(query({criteria}))).toEqual(["a"]);
    expect(ids(query({criteria:[{field:"children",operator:"eq",value:0}]}))).toEqual(["b"]);
    expect(ids(query({criteria:[{field:"children",operator:"unknown",value:null}]}))).toEqual(["d"]);
    expect(ids(query({criteria:[criteria[0],{field:"children",operator:"eq",value:0}],matchMode:"any"}))).toEqual(["a","b"]);
  });
  it("keeps incomplete numeric rules invalid and supports declared choices",()=>{
    expect(searchNodes(nodes,fields,query({criteria:[{field:"children",operator:"gt",value:""}]}),null).valid).toBe(false);
    expect(ids(query({criteria:[{field:"ecosystem",operator:"eq",value:"PyPI"}]}))).toEqual(["a","b"]);
    expect(searchNodes(nodes,fields,query({query:""}),null).active).toBe(false);
  });
});

it("applies stable matches-first order only to eligible visible peer groups",()=>{
  const nodes=["a","b","c","context","small","hidden"].map(id=>({id,type:"package"}));
  const edges=["a","b","c","context","hidden"].map(target=>({source:"parent",target}));
  const applied={matchingIds:["c","small","hidden"],scopeIds:["a","b","c","small","hidden"],visualOrder:["a","context","b","c","small","hidden"]};
  const order=searchOrder(nodes,edges,new Map(),new Set(["hidden"]),applied,3);
  expect([...order.keys()]).toEqual(["c","context","a","b"]);
  expect(searchOrder(nodes,edges,new Map(),new Set(),applied,10).size).toBe(0);
  expect(searchOrder(nodes,edges,new Map(),new Set(),null,3).size).toBe(0);
  expect(searchOrder(nodes,[],new Map(nodes.map(n=>[n.id,"collection"])),new Set(["hidden"]),applied,3).get("c")).toBe(0);
});
