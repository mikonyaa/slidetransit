"use strict";
(() => {
  const payload = JSON.parse(document.getElementById("transit-data").textContent);
  const report = payload.report;
  const $ = id => document.getElementById(id);
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node; };
  const decisions = report.decisions.filter(d => d.state === "applied").map(d => d.decision);
  let pageIndex = 0, selectedId = null, overlay = false;
  const images = payload.images;
  const pageRecord = () => report.pages[pageIndex];
  const currentFinding = () => report.findings.find(f => f.id === selectedId);
  const filtered = () => report.findings.filter(f => (f.page == null || f.page === pageRecord().page) && ($("severity").value === "all" || f.severity === $("severity").value) && ($("state").value === "all" || f.reviewState === $("state").value));
  function toast(message) { $("toast").textContent = message; $("toast").style.display = "block"; clearTimeout(toast.timer); toast.timer = setTimeout(() => { $("toast").style.display = "none"; }, 4200); }
  function updateHeader() {
    $("headline").textContent = report.analysisStatus === "error" ? "Analysis needs attention." : report.summary.findings ? "An export changed." : report.analysisStatus === "incomplete" ? "Coverage needs attention." : "The checked scope agrees.";
    $("subline").textContent = "Inspect two real exports, follow the measured evidence, and record a reason for each decision.";
    $("status").textContent = "Analysis " + report.analysisStatus;
    const open = report.findings.filter(f => f.reviewState === "open").length;
    $("count").textContent = open + " open / " + report.findings.length + " findings";
    $("mode").textContent = report.provenance.mode;
    $("version").textContent = report.tool.version;
    $("comparison").textContent = "COMPARISON " + report.comparisonId.slice(0, 16);
  }
  function renderSlides() {
    $("slides").replaceChildren();
    report.pages.forEach((page, index) => {
      const count = report.findings.filter(f => f.page === page.page).length;
      const button = el("button", null, "slide-button" + (pageIndex === index ? " selected" : ""));
      button.setAttribute("aria-current", pageIndex === index ? "page" : "false");
      button.append(el("span", "Slide " + String(page.page).padStart(2, "0")), el("small", String(count)));
      button.addEventListener("click", () => { pageIndex = index; selectedId = null; overlay = false; render(); });
      $("slides").append(button);
    });
  }
  function imageNode(path, alt) { const image = el("img"); image.src = images[path]; image.alt = alt; return image; }
  function svgBoxes(canvas, page, role) {
    const selected = currentFinding();
    if (!selected || selected.page !== pageRecord().page) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${page.width} ${page.height}`);
    svg.setAttribute("aria-hidden", "true");
    const roles = overlay ? ["reference", "candidate"] : [role];
    roles.forEach(side => {
      const box = selected[side + "BBox"];
      if (!box) return;
      const rect = document.createElementNS(svg.namespaceURI, "rect");
      rect.setAttribute("x", box[0]); rect.setAttribute("y", box[1]);
      rect.setAttribute("width", Math.max(1, box[2] - box[0])); rect.setAttribute("height", Math.max(1, box[3] - box[1]));
      rect.setAttribute("class", side + "-rect"); svg.append(rect);
    });
    canvas.append(svg);
  }
  function renderPages() {
    const record = pageRecord();
    $("page-label").textContent = `SLIDE ${String(record.page).padStart(2, "0")} / ${report.pages.length}`;
    const compatible = record.correspondence === "declared-order" && record.reference && record.candidate && Math.abs(record.reference.width - record.candidate.width) < .25 && Math.abs(record.reference.height - record.candidate.height) < .25;
    $("overlay").disabled = !compatible;
    if (!compatible) overlay = false;
    $("overlay").setAttribute("aria-pressed", String(overlay));
    document.querySelector(".opacity").hidden = !overlay;
    $("correspondence").hidden = record.correspondence === "declared-order";
    $("correspondence").textContent = "Unpaired previews. Page correspondence is unresolved; these indexed pages are not asserted to match.";
    $("pages").className = "pages" + (overlay ? " overlay-mode" : "");
    $("pages").replaceChildren();
    (overlay ? ["reference"] : ["reference", "candidate"]).forEach(role => {
      const page = record[role];
      const pane = el("section", null, "pane" + (!overlay && role !== $("side").value ? " mobile-hidden" : ""));
      const head = el("header"); head.append(el("strong", overlay ? "REFERENCE + CANDIDATE OVERLAY" : role.toUpperCase()), el("small", page ? `${page.width.toFixed(1)} × ${page.height.toFixed(1)} pt` : "Absent")); pane.append(head);
      if (!page) { pane.append(el("p", "No exported page", "empty")); $("pages").append(pane); return; }
      const scroller = el("div", null, "image-scroll"); scroller.tabIndex = 0; scroller.setAttribute("aria-label", role + " page image; scroll when zoomed");
      const canvas = el("div", null, "canvas"); canvas.append(imageNode(page.image, `${role} exported page ${record.page}`));
      if (overlay) { const image = imageNode(record.candidate.image, "Candidate overlay"); image.className = "overlay-image"; image.style.opacity = $("opacity").value / 100; canvas.append(image); }
      svgBoxes(canvas, page, role); scroller.append(canvas); pane.append(scroller); $("pages").append(pane);
    });
  }
  function renderFindings() {
    const list = filtered();
    if (!list.some(f => f.id === selectedId)) selectedId = list.length ? list[0].id : null;
    $("visible-count").textContent = String(list.length);
    $("findings").replaceChildren();
    if (!list.length) $("findings").append(el("p", "No findings in this filter. Check coverage below before treating this as clear.", "empty"));
    list.forEach((item, index) => {
      const button = el("button", null, "finding" + (item.id === selectedId ? " selected" : ""));
      button.dataset.findingId = item.id;
      button.setAttribute("aria-pressed", String(item.id === selectedId));
      button.append(el("span", String(index + 1).padStart(2, "0") + " / " + item.severity, "severity"), el("strong", item.title), el("small", item.ruleId + " · " + item.reviewState));
      button.addEventListener("click", () => { selectedId = item.id; renderFindings(); renderPages(); renderDetail(); });
      $("findings").append(button);
    });
  }
  async function regionHash(page, region) {
    const value = JSON.stringify({page, region: region.map(n => n.toFixed(4))});
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2,"0")).join("");
  }
  function renderDetail() {
    const detail = $("detail"); detail.replaceChildren();
    const item = currentFinding();
    if (!item) { detail.append(el("h3", report.analysisStatus === "complete" ? "Evidence is ready to inspect." : "Read the coverage limits."), el("p", "Choose a slide or adjust the filters. Arrow keys navigate findings; O toggles overlay.", "explanation")); return; }
    detail.append(el("p", item.ruleId + " / RULE " + item.ruleVersion, "category"), el("h3", item.title));
    if (item.reviewState !== "open") detail.append(el("p", "Reviewer " + (item.reviewState === "accepted" ? "accepted this difference" : "accepted this region") + ". The measured evidence remains visible.", "notice"));
    detail.append(el("p", item.evidence.probableExplanation || "Observed difference. This check does not establish an exporter defect or its cause.", "explanation"));
    const crops = el("div", null, "crops");
    ["reference", "candidate"].forEach(role => {
      if (!item.cropReferences[role]) return;
      const figure = el("figure"); figure.append(el("figcaption", role.toUpperCase() + " / LOCALIZED CROP"));
      const frame = el("div", null, "crop-frame"); frame.append(imageNode(item.cropReferences[role], role + " finding crop")); figure.append(frame); crops.append(figure);
    });
    detail.append(crops);
    const measurement = el("details"); measurement.open = true; measurement.append(el("summary", "Measured evidence"), el("pre", JSON.stringify(item.evidence, null, 2))); detail.append(measurement);
    detail.append(el("p", item.attribution.status === "likely" ? `Likely source object: ${item.attribution.slidePart}, shape ${item.attribution.shapeId}. ${item.attribution.basis.join("; ")}. Heuristic association.` : "Source attribution: unattributed. This does not reduce independent PDF comparison coverage.", "attribution"));
    const form = el("div", null, "review-form");
    const reasonLabel = el("label", "Reason (required)"); reasonLabel.htmlFor = "reason";
    const reason = el("textarea"); reason.id = "reason"; reason.maxLength = 2000; reason.placeholder = "Explain why this difference is acceptable.";
    const authorLabel = el("label", "Reviewer name (optional)"); authorLabel.htmlFor = "author";
    const author = el("input", null, "author"); author.id = "author"; author.maxLength = 100;
    const accept = el("button", "Accept difference", "primary"); accept.disabled = true;
    const regionButton = el("button", "Accept limited region"); regionButton.disabled = true;
    const actions = el("div", null, "review-actions"); actions.append(accept, regionButton);
    const regionToggle = el("details"); regionToggle.append(el("summary", "Limited ignore region (points)"));
    const boxes = [item.referenceBBox, item.candidateBBox].filter(Boolean);
    const initial = boxes.length ? [Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))] : [0,0,0,0];
    const regionFields = el("div", null, "region-fields");
    const inputs = ["x0", "y0", "x1", "y1"].map((key,index)=> { const label = el("label", key); const input = el("input"); input.type = "number"; input.step = ".01"; input.value = initial[index].toFixed(4); input.setAttribute("aria-label", "Region " + key); label.append(input); regionFields.append(label); return input; });
    regionToggle.append(regionFields, el("p", "Must fit both pages and cover at most 25%. Cannot accept page absence, parsing errors or unresolved correspondence.", "review-note"));
    function regionValid() { const page = pageRecord(), b = inputs.map(i=>Number(i.value)); return item.page != null && page.correspondence === "declared-order" && page.reference && page.candidate && !["page-correspondence-problem", "page-geometry-change"].includes(item.ruleId) && b.every(Number.isFinite) && b[0]>=0 && b[1]>=0 && b[2]>b[0] && b[3]>b[1] && [page.reference,page.candidate].every(p=>b[2]<=p.width && b[3]<=p.height && (b[2]-b[0])*(b[3]-b[1])<=p.width*p.height*.25); }
    function enable() { accept.disabled = !reason.value.trim(); regionButton.disabled = !reason.value.trim() || !regionValid(); }
    reason.addEventListener("input", enable); inputs.forEach(input=>input.addEventListener("input",enable));
    function baseDecision(type) { const d = {type,reason:reason.value.trim(),timestamp:new Date().toISOString()}; if(author.value.trim())d.author=author.value.trim(); return d; }
    accept.addEventListener("click", () => { if(!reason.value.trim())return; const d = {...baseDecision("accept-difference"), findingId:item.id, regionHash:item.regionHash}; const previous=decisions.findIndex(x=>x.findingId===item.id); if(previous>=0)decisions.splice(previous,1); decisions.push(d); item.reviewState="accepted"; render(); toast("Difference accepted; evidence retained. Download decisions to apply them with the CLI."); });
    regionButton.addEventListener("click", async () => { if(!reason.value.trim() || !regionValid())return; const region=inputs.map(i=>Number(i.value)); const d={...baseDecision("ignore-region"),page:item.page,region,regionHash:await regionHash(item.page,region)}; decisions.push(d); report.findings.filter(f=>f.page===item.page && !["page-correspondence-problem","page-geometry-change"].includes(f.ruleId)).forEach(f=> {const boxes=[f.referenceBBox,f.candidateBBox].filter(Boolean);if(boxes.length && boxes.every(b=>region[0]<=b[0]&&region[1]<=b[1]&&region[2]>=b[2]&&region[3]>=b[3]))f.reviewState="region-accepted";}); render();toast("Bounded region accepted; covered findings remain visible."); });
    form.append(reasonLabel, reason, authorLabel, author, actions, regionToggle, el("p", "Acceptance is tied to these input hashes, rules, renderer and region. Changed evidence requires a new decision.", "review-note")); detail.append(form);
  }
  function renderTechnical() {
    const content = {provenance:report.provenance, coverage:report.coverage, limitations:report.limitations, inputs:report.inputs, renderer:report.renderer, rules:report.rules, configuration:report.config, analysisStatus:report.analysisStatus, savedDecisions:report.decisions, coordinates:report.coordinates, fontLicenses:payload.fontLicenses};
    $("technical").replaceChildren(el("pre",JSON.stringify(content,null,2)));
  }
  function render() { updateHeader(); renderSlides(); renderFindings(); renderPages(); renderDetail(); renderTechnical(); }
  ["severity", "state"].forEach(id => $(id).addEventListener("change", () => { selectedId=null; render(); }));
  $("side").addEventListener("change",renderPages);
  $("overlay").addEventListener("click",()=>{overlay=!overlay;renderPages();});
  $("zoom").addEventListener("change",()=>{document.documentElement.style.setProperty("--zoom",$("zoom").value);});
  $("opacity").addEventListener("input",()=>{document.querySelectorAll(".overlay-image").forEach(i=>{i.style.opacity=$("opacity").value/100;});});
  $("download").addEventListener("click",()=>{
    const document_={schemaVersion:"1.0",comparisonId:report.comparisonId,inputs:report.inputs,rules:report.rules,renderer:report.renderer,decisions};
    const url=URL.createObjectURL(new Blob([JSON.stringify(document_,null,2)+"\n"],{type:"application/json"}));
    const link=el("a");link.href=url;link.download="review-decisions.json";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Review decisions downloaded.");
  });
  document.addEventListener("keydown",event=>{
    if(["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName))return;
    if(event.key.toLowerCase()==="o"&&!$("overlay").disabled){event.preventDefault();$("overlay").click();}
    if(["ArrowRight","ArrowLeft"].includes(event.key)){const list=filtered();if(!list.length)return;event.preventDefault();const i=list.findIndex(f=>f.id===selectedId);selectedId=list[(i+(event.key==="ArrowRight"?1:-1)+list.length)%list.length].id;renderFindings();renderPages();renderDetail();document.querySelector(".finding.selected")?.focus();}
  });
  render();
})();
