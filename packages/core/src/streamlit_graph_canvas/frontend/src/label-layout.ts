export type LabelPolicy={layout:"path"|"wrap"|"single";lines:number;ellipsis:"auto"|"end"|"middle";font_size:number;min_font_size:number|null;reveal_mode:"delayed_hover"|"controls";reveal_delay_ms:number;reveal_hover:boolean;reveal_focus:boolean|null;reveal_button:boolean|null};
export const defaultLabelPolicy:LabelPolicy={layout:"path",lines:2,ellipsis:"auto",font_size:14,min_font_size:null,reveal_mode:"delayed_hover",reveal_delay_ms:600,reveal_hover:true,reveal_focus:null,reveal_button:null};
const segmenter=new Intl.Segmenter(undefined,{granularity:"grapheme"});
const chars=(text:string)=>Array.from(segmenter.segment(text),s=>s.segment);
export function shorten(text:string,width:number,measure:(s:string)=>number,middle:boolean):string {
  if(measure(text)<=width)return text;
  const letters=chars(text);let lo=0,hi=letters.length;
  const candidate=(n:number)=>middle?letters.slice(0,Math.ceil(n/2)).join("")+"…"+letters.slice(letters.length-Math.floor(n/2)).join(""):letters.slice(0,n).join("")+"…";
  while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(measure(candidate(mid))<=width)lo=mid;else hi=mid-1;}
  return measure("…")<=width?candidate(lo):"";
}
export function labelLines(text:string,policy:LabelPolicy,width:number,measure:(s:string)=>number,lineLimit=policy.lines):{lines:string[];truncated:boolean} {
  if(width<=0||lineLimit<1)return {lines:[],truncated:!!text};
  const cut=(s:string,middle:boolean)=>shorten(s,width,measure,middle);
  const slash=Math.max(text.lastIndexOf("/"),text.lastIndexOf("\\"));
  if(policy.layout==="path"&&slash>=0&&slash<text.length-1&&lineLimit>=2){
    const parts=[text.slice(0,slash+1),text.slice(slash+1)];
    let directory=parts[0];
    if(policy.ellipsis!=="end"&&measure(directory)>width){
      const separator=directory.includes("/")?"/":"\\";
      const segments=directory.slice(0,-1).split(separator);
      for(let count=segments.length-1;count>=2;count--){
        const left=Math.ceil(count/2),right=Math.floor(count/2);
        const candidate=[...segments.slice(0,left),"…",...segments.slice(-right)].join(separator)+separator;
        if(measure(candidate)<=width){directory=candidate;break;}
      }
    }
    const lines=[cut(directory,policy.ellipsis!=="end"),cut(parts[1],policy.ellipsis!=="end")];
    return {lines,truncated:lines.some((s,i)=>s!==parts[i])};
  }
  if(policy.layout==="single"||lineLimit===1){const line=cut(text,policy.ellipsis==="middle");return {lines:[line],truncated:line!==text};}
  const remaining=chars(text);const lines:string[]=[];
  while(remaining.length&&lines.length<lineLimit-1){
    if(measure(remaining.join(""))<=width)break;
    let lo=0,hi=remaining.length;
    while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(measure(remaining.slice(0,mid).join(""))<=width)lo=mid;else hi=mid-1;}
    if(lo===0)break;
    const prefix=remaining.slice(0,lo).join("");const boundary=prefix.lastIndexOf(" ");
    const take=boundary>0?chars(prefix.slice(0,boundary+1)).length:lo;
    lines.push(remaining.splice(0,take).join("").trimEnd());
  }
  const rest=remaining.join("");const last=cut(rest,false);if(rest||!lines.length)lines.push(last);
  return {lines,truncated:last!==rest};
}
