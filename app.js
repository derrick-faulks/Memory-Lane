const timeline = document.querySelector("#timeline");
const sentinel = document.querySelector("#sentinel");
const dialog = document.querySelector("#viewer");
const stage = document.querySelector("#stage");
let offset = 0, loading = false, done = false, items = [], active = -1, lastHeading = "";

const fmtDay = ts => new Intl.DateTimeFormat(undefined,{weekday:"long",month:"long",day:"numeric",year:"numeric"}).format(new Date(ts*1000));
const fmtMonth = ts => new Intl.DateTimeFormat(undefined,{month:"long",year:"numeric"}).format(new Date(ts*1000));

async function status() {
  const s = await fetch("/api/status").then(r=>r.json());
  document.querySelector("#total").textContent = s.total.toLocaleString();
  document.querySelector("#status").textContent = s.message;
  document.querySelector("#folder").textContent = s.library || "No library selected";
  document.querySelector(".dot").classList.toggle("busy", s.scanning);
  if (s.first) {
    const a = new Date(s.first*1000).getFullYear(), b = new Date(s.last*1000).getFullYear();
    document.querySelector("#range").textContent = a === b ? a : `${a}—${b}`;
    const year = document.querySelector("#year"), current = year.value;
    if (year.options.length === 1) for(let y=b;y>=a;y--) year.add(new Option(y,y));
    year.value = current;
  }
  if (s.scanning) setTimeout(status, 1200);
}

function reset() {
  offset=0; done=false; items=[]; active=-1; lastHeading=""; timeline.innerHTML="";
  load();
}

async function load() {
  if (loading || done) return;
  loading=true;
  const kind=document.querySelector("#kind").value, year=document.querySelector("#year").value;
  const batch=await fetch(`/api/media?offset=${offset}&limit=120&kind=${kind}&year=${year}`).then(r=>r.json());
  if (!batch.length) done=true;
  batch.forEach(item => {
    const heading=fmtMonth(item.taken);
    if (heading!==lastHeading) {
      const h=document.createElement("h2"); h.textContent=heading; timeline.append(h); lastHeading=heading;
    }
    const card=document.createElement("button"); card.className="card";
    card.innerHTML = item.thumb
      ? `<img loading="lazy" src="/thumb/${item.thumb}" alt=""><span class="shade"></span>`
      : `<div class="placeholder">${item.kind==="video"?"▶":"◇"}</div>`;
    card.insertAdjacentHTML("beforeend", `<span class="date">${fmtDay(item.taken)}</span>${item.kind==="video"?'<span class="play">▶</span>':""}`);
    card.onclick=()=>openItem(items.indexOf(item));
    timeline.append(card); items.push(item);
  });
  offset+=batch.length; loading=false;
  document.querySelector("#empty").hidden = items.length > 0;
}

function openItem(index) {
  if(index<0 || index>=items.length) return;
  active=index; const item=items[index];
  stage.innerHTML=item.kind==="video"
    ? `<video src="/media/${item.id}" controls autoplay></video>`
    : `<img src="/media/${item.id}" alt="">`;
  document.querySelector("#caption").textContent=`${item.name}  ·  ${fmtDay(item.taken)}  ·  Date from ${item.date_source}`;
  dialog.showModal();
}

document.querySelector("#close").onclick=()=>dialog.close();
document.querySelector("#prev").onclick=()=>openItem(active-1);
document.querySelector("#next").onclick=()=>openItem(active+1);
dialog.onclick=e=>{if(e.target===dialog)dialog.close()};
document.addEventListener("keydown",e=>{
  if(!dialog.open)return;
  if(e.key==="ArrowLeft")openItem(active-1);
  if(e.key==="ArrowRight")openItem(active+1);
});
document.querySelector("#kind").onchange=reset;
document.querySelector("#year").onchange=reset;
document.querySelector("#scan").onclick=async()=>{await fetch("/api/scan",{method:"POST"});status()};
document.querySelector("#library").onclick=async()=>{
  const result=await fetch("/api/library",{method:"POST"}).then(r=>r.json());
  if(result.changed){reset();status()}
};
document.querySelector("#quit").onclick=async()=>{
  await fetch("/api/shutdown",{method:"POST"});
  document.body.innerHTML='<div id="stopped"><h1>Memory Lane has stopped.</h1><p>You may close this window.</p></div>';
};
new IntersectionObserver(entries=>{if(entries[0].isIntersecting)load()},{rootMargin:"900px"}).observe(sentinel);
status(); load();
