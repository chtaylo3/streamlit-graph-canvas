import {it,expect} from "vitest";
import {defaultLabelPolicy as defaults,labelLines,shorten} from "./label-layout";
const measure=(s:string)=>Array.from(s).length;
it("keeps a filename intact and shortens the middle of its directory",()=>{
  expect(labelLines("src/integrations/prefect/infra/packages-lock.json",defaults,20,measure).lines).toEqual(["src/…/infra/","packages-lock.json"]);
});
it("shortens long filenames in the middle, retaining their extension",()=>{
  const result=labelLines("src/Microsoft.PowerToys.Tests.csproj",defaults,20,measure);
  expect(result.lines[1].endsWith(".csproj")).toBe(true);
  expect(result.lines[1]).toContain("…");
});
it("wraps ordinary names with end ellipsis and respects width",()=>{
  const result=labelLines("a very long ordinary display name",defaults,10,measure);
  expect(result.lines).toHaveLength(2);expect(result.lines[1].endsWith("…")).toBe(true);
  expect(result.lines.every(s=>measure(s)<=10)).toBe(true);
});
it("supports end and middle single-line policies and Windows paths",()=>{
  expect(labelLines("abcdefghijkl",{...defaults,layout:"single",lines:1,ellipsis:"middle"},7,measure).lines).toEqual(["abc…jkl"]);
  expect(labelLines("C:\\long\\directory\\file.txt",defaults,12,measure).lines[1]).toBe("file.txt");
  expect(shorten("hello",2,measure,false)).toBe("h…");
});
it("handles tiny boxes, empty labels, and whole unicode graphemes",()=>{
  expect(labelLines("text",defaults,0,measure).lines).toEqual([]);
  expect(labelLines("",defaults,10,measure).truncated).toBe(false);
  expect(shorten("👩‍💻👩‍💻abc",4,measure,false)).toBe("👩‍💻…");
});
