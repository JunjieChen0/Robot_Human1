import {VERSION, RULES, SquatCounter, kneeObservation} from "./counter.mjs";

const $ = id => document.getElementById(id);
const video = $("video"), canvas = $("canvas"), ctx = canvas.getContext("2d");
const answerIds = ["participant", "hints", "taskCompleted", "noticedError", "correctionAnswer", "issues"];
let modelHash = null, worker = null, workerReady = false, initialization = null, inferenceMode = null;
let mediaStream = null, objectUrl = null, source = null, session = null;
let counter = new SquatCounter(), trace = [], actions = [], savedAnswers = null;
let state = "idle", epoch = 0, busy = false, lastSourceMs = null, lastCaptureWall = 0, lastModelMs = 0;
let pausedAt = 0, lastHeight = 0;
let countNotice = "", countNoticeUntil = 0;

function bridge(type, rest = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...rest}, "*");
}
function resize() {
  const height = Math.ceil($("app").getBoundingClientRect().height) + 20;
  if (height !== lastHeight) { lastHeight = height; bridge("streamlit:setFrameHeight", {height}); }
}
new ResizeObserver(resize).observe($("app"));
bridge("streamlit:componentReady", {apiVersion: 1});
window.addEventListener("message", event => {
  if (event.source === window.parent && event.data?.type === "streamlit:render") {
    modelHash = event.data.args.model_sha256;
    resize();
  }
});

function timeLabel(ms) {
  const seconds = Math.max(0, ms)/1000;
  return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${(seconds%60).toFixed(1).padStart(4,"0")}`;
}
function feedback(text, warning = false) {
  if ($("feedback").textContent !== text) $("feedback").textContent = text;
  $("feedback").classList.toggle("warning", warning);
}
function logAction(kind, extra = {}) {
  if (session) actions.push({kind, time_ms: video.currentTime*1000, wall_time_iso: new Date().toISOString(), ...extra});
}
function controls() {
  const running = state === "running", paused = state === "paused", ended = state === "ended";
  const editable = Boolean(session) && (paused || ended);
  $("start").disabled = !source || !$("consent").checked || running || paused || state === "loading" || (source.kind === "camera" && !mediaStream);
  $("start").textContent = ended ? "重新计数（清空本次记录）" : "开始计数";
  $("pause").disabled = !running;
  $("resume").disabled = !paused;
  $("end").disabled = !["running","paused","loading"].includes(state);
  $("closeCamera").disabled = !mediaStream;
  $("sourceMode").disabled = running || paused || state === "loading";
  $("side").disabled = running || paused || state === "loading";
  $("file").disabled = !$("consent").checked || running || paused || state === "loading";
  $("openCamera").disabled = !$("consent").checked || running || paused || state === "loading";
  $("add").disabled = !editable;
  $("retract").disabled = !editable || !$("eventChoice").value;
  $("eventChoice").disabled = !editable;
  $("undoCorrection").disabled = !editable || counter.activeCorrections.length === 0;
  $("download").disabled = !editable;
  $("saveAnswers").disabled = !editable || Boolean(savedAnswers);
  $("reviewLabel").hidden = !source || source.kind !== "video" || !editable;
  $("cameraStatus").textContent = mediaStream ? `摄像头：开启${paused ? "（识别已暂停）" : ""}` : "摄像头：关闭";
  $("cameraStatus").classList.toggle("active", Boolean(mediaStream));
}
function renderCounts() {
  $("autoCount").textContent = counter.events.length;
  $("correctedCount").textContent = counter.correctedTotal;
  $("adjustment").textContent = `手工净调整 ${counter.correctedTotal - counter.events.length} 次；自动记录始终保留。`;
  const selected = $("eventChoice").value;
  $("eventChoice").replaceChildren();
  const available = counter.events.filter(e => !counter.isRetracted(e.id));
  if (!available.length) $("eventChoice").add(new Option("暂无可撤销自动记录", ""));
  for (const event of available) $("eventChoice").add(new Option(`${event.id} · ${timeLabel(event.time_ms)}`, event.id));
  if (available.some(e => e.id === selected)) $("eventChoice").value = selected;
  else if (available.length) $("eventChoice").value = available.at(-1).id;
  const entries = [
    ...counter.events.map(e => ({time: e.time_ms, text: `${timeLabel(e.time_ms)} 自动 +1（${e.id}）${counter.isRetracted(e.id) ? "，已标为误计" : ""}`})),
    ...counter.corrections.map(c => ({time: c.time_ms, text: `${timeLabel(c.time_ms)} ${c.kind === "add_manual" ? "补记漏计 +1" : c.kind === "retract_auto" ? "撤销误计 -1：" + c.target_id : "撤销上次修正：" + c.target_id}`}))
  ].sort((a,b) => a.time-b.time);
  $("eventLog").replaceChildren(...entries.map(entry => { const li = document.createElement("li"); li.textContent = entry.text; return li; }));
  $("sessionState").textContent = session ? `${state === "ended" ? "已结束" : state === "paused" ? "已暂停" : "进行中"} · ${session.id} · 有效/无效帧均保留在导出记录` : "还没有开始计数。";
  controls();
}
function stopTracks() {
  if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());
  mediaStream = null;
  video.srcObject = null;
}
function end(reason = "user_end") {
  epoch++;
  video.pause();
  dropWorker();
  counter.invalidate("ended");
  logAction(reason);
  state = session ? "ended" : "idle";
  if (session) session.ended_at = new Date().toISOString();
  stopTracks();
  feedback(session ? "本次计数已结束。可回看视频、修正并导出；摄像头已关闭。" : "输入已关闭，摄像头未工作。");
  renderCounts();
}
function clearSession() {
  counter = new SquatCounter(); trace = []; actions = []; session = null; savedAnswers = null;
  countNoticeUntil=0;
  answerIds.forEach(id => { $(id).disabled = false; $(id).value = ""; });
  $("answerState").textContent = "";
  lastSourceMs = null;
  renderCounts();
}
function dropWorker() {
  worker?.terminate(); worker = null; workerReady = false; initialization = null; busy = false; inferenceMode = null;
  $("modelStatus").textContent = "模型：尚未加载";
}
function drawFrame() {
  if (video.readyState < 2 || !video.videoWidth) return;
  const scale = Math.min(1, 640/video.videoWidth);
  const width = Math.round(video.videoWidth*scale), height = Math.round(video.videoHeight*scale);
  if (canvas.width !== width || canvas.height !== height) {canvas.width = width; canvas.height = height;}
  ctx.drawImage(video, 0, 0, width, height);
  $("clock").textContent = `片段时间 ${timeLabel(video.currentTime*1000)}`;
}
function drawPoints(points) {
  if (!points) return;
  ctx.strokeStyle = "#39e4b4"; ctx.fillStyle = "#39e4b4"; ctx.lineWidth = 4;
  ctx.beginPath(); points.forEach((p,i) => { if (i === 0) ctx.moveTo(p.x*canvas.width,p.y*canvas.height); else ctx.lineTo(p.x*canvas.width,p.y*canvas.height); }); ctx.stroke();
  for (const p of points) { ctx.beginPath(); ctx.arc(p.x*canvas.width,p.y*canvas.height,5,0,Math.PI*2);ctx.fill(); }
}
function showObservation(observation, result) {
  $("angle").textContent = observation.valid ? `膝角 ${observation.angle.toFixed(1)}°` : "膝角 —";
  if (!observation.valid) {
    countNoticeUntil=0;
    const messages = {no_pose:"未可靠识别人形。请侧身、后退，让肩髋膝踝完整入镜。", multiple_people:"画面有多人，请只保留一位使用者。",
      low_visibility:"肩髋膝踝不够清楚，请移开遮挡、调整光照或转为侧身。", out_of_frame:"关键点接近画面边缘，请后退或调整摄像头。", degenerate:"关键点位置异常，请重新调整位置。"};
    feedback(`看不清，已暂停计数。${messages[observation.reason] || "请调整位置。"}恢复后先站立准备。`,true);
  } else if (result.phase === "need_stand") feedback("先站立并保持片刻，准备下一次。暂停、遮挡或画面跳变后都需要重新准备。");
  else if (result.event) {
    countNotice=`已完成1次，自动计数 ${counter.events.length}。请站稳后开始下一次。`;
    countNoticeUntil=performance.now()+1000;feedback(countNotice);
  }
  else if (result.phase === "down") feedback("已确认下蹲，恢复站立后计1次。保持不重复计数。");
  else if (performance.now()<countNoticeUntil) feedback(countNotice);
  else feedback("已准备。下蹲后恢复站立，完成一次完整动作。");
}
function ensureWorker() {
  if (workerReady) return Promise.resolve();
  if (initialization) return initialization;
  initialization = new Promise((resolve, reject) => {
    worker = new Worker(new URL("./pose_worker.mjs", import.meta.url));
    $("modelStatus").textContent = "模型：正在加载并校验，请稍候";
    worker.onmessage = ({data}) => {
      if (data.kind === "ready") {
        inferenceMode=data.inference_mode;
        workerReady = true; $("modelStatus").textContent = inferenceMode === "mediapipe" ? "模型：CPU已就绪" : "模型：测试模拟，非真实识别"; resolve();
      } else if (data.kind === "error") {
        logAction("model_error",{message:data.message});
        busy = false; reject(new Error(data.message));
        if (state === "running") pause();
        feedback(`模型未能处理画面：${data.message}。可关闭输入，检查资源后重试。`,true);
        dropWorker(); controls();
      } else if (data.kind === "result") {
        busy = false;
        if (data.epoch !== epoch || state !== "running") return;
        const observation = data.landmarks.length > 1 ? {valid:false,reason:"multiple_people"}
          : kneeObservation(data.landmarks[0],data.width,data.height,$("side").value);
        const result = counter.observe({...observation,timeMs:data.frameTimeMs});
        drawPoints(observation.points);
        trace.push({time_ms:data.frameTimeMs,valid:observation.valid,reason:observation.reason || "",angle:observation.angle ?? null,
          visibility:observation.visibility ?? null,points:observation.points ?? null,phase:result.phase});
        showObservation(observation,result);
        if (result.event) {
          renderCounts();
          // Software estimate at a subsequent render callback, not optical screen timing.
          requestAnimationFrame(() => requestAnimationFrame(() => {
            const pipeline = performance.now()-data.captureWallMs;
            result.event.frame_pipeline_ms = pipeline;
            result.event.feedback_time_ms = data.frameTimeMs + pipeline;
          }));
        }
        if (video.ended) end("video_finished");
      }
    };
    worker.onerror = error => {
      logAction("model_error",{message:error.message});
      reject(new Error(error.message || "浏览器模型线程未启动"));
      if (state === "running") pause();
      feedback("模型线程启动失败。请检查下载资源与浏览器控制台，输入可关闭。",true);
      dropWorker();controls();
    };
    worker.postMessage({kind:"init",modelHash});
  });
  return initialization;
}
async function start(resume = false) {
  if (!source || !$("consent").checked) return;
  const activeEpoch = ++epoch;
  state = "loading"; controls();feedback("正在准备模型，计数尚未开始。");
  try {
    await ensureWorker();
    if (activeEpoch !== epoch) return;
    if (!resume) {
      clearSession();
      session = {id:crypto.randomUUID(),started_at:new Date().toISOString(),ended_at:null,
        source:{...source},rules:{...RULES,side:$("side").value},
        model:{package:"@mediapipe/tasks-vision",version:"0.10.32",variant:"pose_landmarker_lite/float16/1",
          sha256:modelHash,delegate:"CPU",inference_mode:inferenceMode}};
      if (source.kind === "video") video.currentTime=0;
    } else if (source.kind === "video") video.currentTime=pausedAt;
    counter.invalidate(resume ? "resume" : "start");lastSourceMs=null;
    video.playbackRate=1;await video.play();
    if (activeEpoch !== epoch) { video.pause();return; }
    state="running";logAction(resume?"resume":"start");feedback("请先站立准备，再完成下蹲并恢复站立。");renderCounts();
  } catch(error) {
    if(activeEpoch!==epoch)return;
    state=session?"paused":"idle";feedback(`无法开始：${error.message}。请使用localhost或HTTPS，确认资源已下载。`,true);controls();
  }
}
function pause() {
  if (state !== "running") return;
  pausedAt=video.currentTime;video.pause();epoch++;state="paused";counter.invalidate("pause");logAction("pause");
  feedback("识别已暂停，可回看并修正。继续时回到暂停位置，并先站立准备。");renderCounts();
}
async function loadFile() {
  const file=$("file").files[0];if(!file || !$("consent").checked)return;
  end("change_source");dropWorker();if(objectUrl)URL.revokeObjectURL(objectUrl);
  clearSession();source=null;state="loading";
  const activeEpoch=epoch;
  $("sourceInfo").textContent="正在校验视频身份，请稍候。";controls();
  try {
    if (!crypto.subtle) throw new Error("请通过localhost或HTTPS打开页面");
    const sha=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",await file.arrayBuffer())),b=>b.toString(16).padStart(2,"0")).join("");
    if(activeEpoch!==epoch)return;
    objectUrl=URL.createObjectURL(file);video.src=objectUrl;video.load();
    await new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(new Error("浏览器无法解码，请使用MP4(H.264)或WebM"));});
    if(activeEpoch!==epoch)return;
    source={kind:"video",name:file.name,sha256:sha,size_bytes:file.size,duration_ms:video.duration*1000,consent_confirmed:true};
    state="idle";
    $("review").max=video.duration;$("sourceInfo").textContent=`已载入 ${file.name} · ${timeLabel(source.duration_ms)}。点击开始，视频以1倍速识别。`;
    drawFrame();feedback("视频已就绪，开始后先确认站立。",false);controls();
  } catch(error) {
    if(activeEpoch!==epoch)return;
    state="idle";feedback(error.message,true);$("sourceInfo").textContent="视频未准备成功，可重新选择。";controls();
  }
}
async function openCamera() {
  if(!$("consent").checked)return;
  end("change_source");dropWorker();clearSession();source=null;
  const activeEpoch=epoch;
  state="loading";controls();feedback("正在等待摄像头授权，可取消同意或点击结束关闭输入。");
  if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=null;}
  controls();
  try {
    if(!navigator.mediaDevices?.getUserMedia)throw new Error("摄像头需要localhost或HTTPS安全连接");
    const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:false});
    if(activeEpoch!==epoch || !$("consent").checked || $("sourceMode").value!=="camera") {stream.getTracks().forEach(t=>t.stop());return;}
    mediaStream=stream;video.removeAttribute("src");video.srcObject=stream;await video.play();
    source={kind:"camera",name:"浏览器摄像头",sha256:null,consent_confirmed:true};state="idle";
    $("sourceInfo").textContent="摄像头已开启，尚未计数。侧身完整入镜后点击开始；画面默认不保存。";
    feedback("摄像头已开启，点击开始后计数。");controls();
  } catch(error) {
    if(activeEpoch!==epoch)return;
    stopTracks();state="idle";
    feedback(`无法打开摄像头：${error.message}。可导入测试视频，或检查权限与连接。`,true);controls();
  }
}
async function loop() {
  requestAnimationFrame(loop);
  if(state==="running" && workerReady && !busy && video.readyState>=2 && !video.paused && performance.now()-lastCaptureWall>=60) {
    const time=video.currentTime*1000;if(lastSourceMs===time)return;
    busy=true;lastSourceMs=time;lastCaptureWall=performance.now();const capturedEpoch=epoch;
    drawFrame();
    try {
      const bitmap=await createImageBitmap(canvas);
      if(capturedEpoch!==epoch || state!=="running") {bitmap.close();busy=false;return;}
      lastModelMs=Math.max(lastModelMs+1,performance.now());
      worker.postMessage({kind:"frame",bitmap,epoch:capturedEpoch,frameTimeMs:time,captureWallMs:lastCaptureWall,
        modelTimeMs:lastModelMs,width:canvas.width,height:canvas.height},[bitmap]);
    } catch(error) {busy=false;pause();feedback(`画面读取失败：${error.message}`,true);}
  } else if(mediaStream && state==="idle" && video.readyState>=2) drawFrame();
}

$("consent").onchange=()=>{if(!$("consent").checked)end("consent_withdrawn");controls();};
$("sourceMode").onchange=()=>{
  end("change_mode");dropWorker();clearSession();source=null;
  const cameraMode=$("sourceMode").value==="camera";
  $("fileLabel").hidden=cameraMode;$("openCamera").hidden=!cameraMode;
  $("sourceInfo").textContent=cameraMode?"请打开摄像头，侧身完整入镜后开始。":"请选择视频，载入后再开始。";
  ctx.clearRect(0,0,canvas.width,canvas.height);$("clock").textContent="片段时间 00:00.0";$("angle").textContent="膝角 —";
  feedback("等待新输入，请先确认影像使用同意。");controls();
};
$("file").onchange=loadFile;$("openCamera").onclick=openCamera;
$("start").onclick=()=>start();$("pause").onclick=pause;$("resume").onclick=()=>start(true);
$("end").onclick=()=>end();$("closeCamera").onclick=()=>end("close_camera");
video.onended=()=>{if(state==="running" && !busy)end("video_finished");};
$("review").oninput=()=>{if(["paused","ended"].includes(state))video.currentTime=Number($("review").value);};
video.onseeked=()=>{if(state!=="running")drawFrame();};
$("eventChoice").onchange=controls;
$("retract").onclick=()=>{const item=counter.correct("retract_auto",video.currentTime*1000,$("eventChoice").value);logAction("retract_auto",{correction_id:item.id,target_id:item.target_id});renderCounts();};
$("add").onclick=()=>{const item=counter.correct("add_manual",video.currentTime*1000);logAction("add_manual",{correction_id:item.id});renderCounts();};
$("undoCorrection").onclick=()=>{const item=counter.undoCorrection(video.currentTime*1000);logAction("undo_correction",{correction_id:item?.id,target_id:item?.target_id});renderCounts();};
$("saveAnswers").onclick=()=>{
  if(!$("participant").value.trim() || !$("taskCompleted").value || !$("noticedError").value.trim() || !$("correctionAnswer").value.trim()) {
    $("answerState").textContent="请填写匿名编号、完成情况、错误核对和修正说明；没有错误可明确写无。";return;
  }
  if(!$("hints").validity.valid) {$("answerState").textContent="提示次数需为非负整数，未知可留空。";return;}
  savedAnswers=Object.fromEntries(answerIds.map(id=>[id,id==="hints"?($(id).value===""?null:Number($(id).value)):$(id).value]));
  savedAnswers.saved_at=new Date().toISOString();answerIds.forEach(id=>$(id).disabled=true);
  $("answerState").textContent="首次反馈已锁定，请导出。新参与者使用新的浏览器会话。";controls();
};
$("download").onclick=()=>{
  logAction("export");
  const report={page_version:VERSION,record_type:"参与者自报及浏览器操作记录；非自动判分",session,source:session.source,
    model:session.model,
    rules:session.rules,automatic_count:counter.events.length,corrected_count:counter.correctedTotal,
    auto_events:counter.events,corrections:counter.corrections,frame_trace:trace,actions,participant_answers:savedAnswers,
    browser:navigator.userAgent,feedback_timing:"feedback_time_ms = source frame time + pipeline elapsed to subsequent render callback; software estimate at 1x playback, not optical measurement"};
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download=`squat_${session.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener("pagehide",()=>{epoch++;stopTracks();worker?.terminate();if(objectUrl)URL.revokeObjectURL(objectUrl);});
window.addEventListener("beforeunload",()=>{epoch++;stopTracks();});
controls();renderCounts();loop();
