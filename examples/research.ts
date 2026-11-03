// Node 24: node examples/research.ts (no third-party client required).
type Research = {status:string; method:string; claims:{text:string;passage_ids:string[]}[];coverage_gaps:string[]};
const base=process.env.LEGAL_AI_BASE_URL || "http://127.0.0.1:8000";
const sessionResponse=await fetch(base+"/v1/sessions",{
  method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({label:"TypeScript SDK example"}),signal:AbortSignal.timeout(30_000),
});
if(!sessionResponse.ok)throw new Error("Local session failed: "+sessionResponse.status);
const session=await sessionResponse.json() as {access_token:string};
const response=await fetch(base+"/v1/research",{
  method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+session.access_token},
  body:JSON.stringify({question:"What paperwork must accompany a security deposit deduction?",jurisdiction:"US-CA",source_scope:"public",configuration:"lexical",top_k:5}),
  signal:AbortSignal.timeout(30_000),
});
if(!response.ok)throw new Error("Research failed: "+response.status);
const result=await response.json() as Research;
console.log("Status:",result.status,"Method:",result.method);
console.log("Coverage gaps:",result.coverage_gaps);
for(const claim of result.claims)console.log("Source quote:",claim.text,"Versioned passages:",claim.passage_ids);
console.log("No independent semantic support or legal applicability claim is made.");
export {};
