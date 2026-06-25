<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/lib.php';
airadio_handle_login();
$auth = airadio_auth();
$allowed = !empty($auth['allowed']);
$loginUrl = isset($auth['login_url']) ? $auth['login_url'] : '?demo_login=xb_bittensor';
$logoutUrl = isset($auth['logout_url']) ? $auth['logout_url'] : '?demo_logout=1';
$sessionUser = isset($auth['session_user']) ? $auth['session_user'] : '';
$isAdmin = !empty($auth['is_admin']);
?>
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kurage AI VTuber Radio</title>
<style>
:root{--ink:#17324d;--muted:#66839a;--sea:#55c7da;--aqua:#e9fbff;--line:#cbeef4;--accent:#2aa8c7;--paper:rgba(255,255,255,.82)}
*{box-sizing:border-box} body{margin:0;min-height:100vh;color:var(--ink);font-family:"Hiragino Sans","Yu Gothic",Meiryo,sans-serif;background:radial-gradient(circle at 18% 10%,#fff 0,#f3fcff 28%,transparent 45%),linear-gradient(140deg,#ffffff 0%,#eefbff 45%,#f9fff9 100%);overflow-x:hidden}.shell{max-width:1180px;margin:0 auto;padding:22px}.hero{display:grid;grid-template-columns:1fr 360px;gap:20px;align-items:stretch}.card{background:var(--paper);border:1px solid var(--line);box-shadow:0 24px 80px rgba(42,168,199,.14);border-radius:28px;padding:22px;backdrop-filter:blur(18px)}.brand{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}.brand h1{font-size:clamp(28px,4vw,54px);line-height:1;margin:0;letter-spacing:.02em}.tag{display:inline-flex;padding:8px 12px;border-radius:999px;background:#fff;border:1px solid var(--line);color:var(--accent);font-weight:700}.lead{font-size:18px;line-height:1.9;color:#35536a;max-width:760px}.controls{display:grid;grid-template-columns:1fr 160px;gap:12px;margin-top:18px}.controls textarea,.controls input,.controls select{width:100%;border:1px solid var(--line);border-radius:16px;padding:14px 15px;background:#fff;color:var(--ink);font-size:15px}.controls textarea{min-height:118px;resize:vertical;line-height:1.7}.liveControls{margin-top:14px;display:grid;grid-template-columns:1fr auto auto;gap:10px}.liveControls input{width:100%;border:1px solid var(--line);border-radius:999px;padding:12px 15px;background:#fff}.buttons{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.btn{border:0;border-radius:999px;padding:12px 18px;font-weight:800;cursor:pointer;background:var(--ink);color:#fff}.btn.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}.btn.live{background:linear-gradient(135deg,#2aa8c7,#76d7c4)}.avatarStage{position:relative;min-height:560px;overflow:hidden;background:linear-gradient(180deg,#fff 0%,#eafcff 100%)}.orb{position:absolute;border-radius:999px;background:rgba(85,199,218,.16);filter:blur(1px)}.orb.one{width:260px;height:260px;right:-70px;top:-50px}.orb.two{width:160px;height:160px;left:-40px;bottom:50px}.avatar{position:absolute;left:50%;bottom:-8px;transform:translateX(-50%);width:min(88%,420px);filter:drop-shadow(0 22px 40px rgba(42,168,199,.22));transition:transform .16s ease}.avatar.talking{transform:translateX(-50%) translateY(-5px) scale(1.012)}.status{position:absolute;left:18px;right:18px;top:18px;background:rgba(255,255,255,.74);border:1px solid var(--line);border-radius:18px;padding:12px}.meter{height:8px;background:#dcf4f7;border-radius:999px;overflow:hidden;margin-top:8px}.meter span{display:block;height:100%;width:18%;background:linear-gradient(90deg,#46c2d8,#a1e7d8);border-radius:999px;transition:width .2s}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.log{height:220px;overflow:auto;font-size:14px;line-height:1.7;color:#3c6075}.segment{padding:10px 0;border-bottom:1px solid #dff3f7}.small{font-size:13px;color:var(--muted)}.locked{display:grid;place-items:center;min-height:70vh;text-align:center}.locked .card{max-width:620px}.now{font-size:18px;font-weight:800}.sleepNote{margin-top:18px;padding:16px;border-radius:20px;background:#f7fffd;border:1px solid #d7f5ef;color:#426}
@media(max-width:900px){.hero,.grid{grid-template-columns:1fr}.avatarStage{min-height:480px}.controls{grid-template-columns:1fr}.shell{padding:12px}.brand{align-items:flex-start;flex-direction:column}}
</style>
</head>
<body>
<?php if (!$allowed): ?>
  <main class="locked shell"><section class="card"><span class="tag">Kurage AI VTuber Radio</span><h1>AI思考のラジオを聴く</h1><p class="lead">共通ログイン後、Kurageが <b>@xb_bittensor</b> のXプロフィールをもとに構成したラジオを再生します。どのアカウントでログインしても同じ番組を聴けます。</p><a class="btn" href="<?= htmlspecialchars($loginUrl) ?>">共通ログイン</a></section></main>
<?php else: ?>
<main class="shell">
  <section class="hero">
    <div class="card">
      <div class="brand"><div><span class="tag">聴きながらよく寝れる</span><h1>Kurage AI<br>VTuber Radio</h1></div><a class="btn secondary" href="<?= htmlspecialchars($logoutUrl) ?>">logout @<?= htmlspecialchars($sessionUser) ?></a></div>
      <p class="lead">Kurageが話し手、@xb_bittensor が聞き手です。Kurage AgentReachで情報収集しながら、Xプロフィールに沿ったAI、Bittensor、バイブコーディング、Web3収益化の話題をラジオのように話し続けます。</p>
      <?php if ($isAdmin): ?>
      <div class="controls"><textarea id="theme" placeholder="割り込ませたいテーマがあれば入力。空白のまま開始すると、@xb_bittensor のXプロフィールからテーマを作ります。"></textarea><select id="hours"><option value="1">1時間</option><option value="2">2時間</option><option value="3">3時間</option><option value="4">4時間</option><option value="5">5時間</option><option value="6">6時間</option></select></div>
      <div class="buttons"><button class="btn live" id="startBtn">ラジオ開始</button><button class="btn secondary" id="interruptBtn">テーマ割り込み</button><button class="btn secondary" id="stopBtn">停止</button></div>
      <div class="liveControls"><input id="streamKey" type="password" placeholder="YouTube Live ストリームキー"><button class="btn secondary" id="youtubeStartBtn">YouTube配信</button><button class="btn secondary" id="youtubeStopBtn">配信停止</button></div>
      <?php else: ?>
      <div class="buttons"><button class="btn live" id="listenBtn">視聴開始</button></div>
      <div class="sleepNote">この画面は視聴専用です。@xb_bittensor が配信開始している間、同じ現在台本を取得して読み上げます。配信していないときは待機中になります。</div>
      <?php endif; ?>
      <div class="sleepNote">眠るためのラジオなので、声は穏やかに、話題は深く、テンポはゆっくり。Kurage AgentReachの情報収集が遅くても、表の話は止めません。</div>
    </div>
    <div class="card avatarStage"><div class="orb one"></div><div class="orb two"></div><div class="status"><div class="small">ON AIR STATUS</div><div class="now" id="nowTalking">待機中</div><div class="small" id="researchStatus">research: idle</div><div class="meter"><span id="meter"></span></div></div><img id="avatar" class="avatar" src="assets/kurage_radio_idle.png" alt="Kurage AI VTuber"></div>
  </section>
  <section class="grid"><div class="card"><h2>次に話す内容</h2><div id="currentText" class="log"></div></div><div class="card"><h2>Loop Log</h2><div id="loopLog" class="log"></div></div></section>
</main>
<script>
const IS_ADMIN = <?= $isAdmin ? 'true' : 'false' ?>;
const api = (action, body) => fetch(`api.php?action=${action}`, {method: body ? 'POST':'GET', headers:{'Content-Type':'application/json'}, body: body ? JSON.stringify(body): undefined}).then(r=>r.json());
const avatar = document.getElementById('avatar');
const nowTalking = document.getElementById('nowTalking');
const currentText = document.getElementById('currentText');
const loopLog = document.getElementById('loopLog');
const researchStatus = document.getElementById('researchStatus');
const meter = document.getElementById('meter');
let running = false; let endsAt = 0; let speaking = false; let lastCurrentId = '';
const bridgeTexts = ['少しだけ、静かな間を置きます。考えは急がなくて大丈夫です。','裏側で情報を集めています。こちらでは、今のテーマをゆっくりほどいていきます。'];
function log(msg){ const el=document.createElement('div'); el.className='segment'; el.textContent=new Date().toLocaleTimeString()+'  '+msg; loopLog.prepend(el); }
function setMouth(on){ avatar.src = on ? 'assets/kurage_radio_talk.png' : 'assets/kurage_radio_idle.png'; avatar.classList.toggle('talking', on); meter.style.width = on ? '78%' : '18%'; }
function speakText(text, title=''){
  return new Promise(resolve=>{
    const u = new SpeechSynthesisUtterance(text); u.lang='ja-JP'; u.rate=.82; u.pitch=1.02; u.volume=.92;
    u.onstart=()=>{ speaking=true; setMouth(true); nowTalking.textContent=title||'話しています'; currentText.textContent=text; };
    u.onend=()=>{ speaking=false; setMouth(false); resolve(); };
    u.onerror=()=>{ speaking=false; setMouth(false); resolve(); };
    speechSynthesis.speak(u);
  });
}
async function radioLoop(){
  while(running && Date.now() < endsAt){
    if (speechSynthesis.paused) speechSynthesis.resume();
    let d; try { d = await api('next'); } catch(e) { d = {item:{title:'ブリッジ',text:bridgeTexts[Math.floor(Math.random()*bridgeTexts.length)]}}; }
    const item = d.item || {}; log(`${item.source||'segment'}: ${item.title||''}`);
    await speakText(item.text || bridgeTexts[0], item.title || 'Kurage Radio');
    await new Promise(r=>setTimeout(r, 900));
  }
  running=false; nowTalking.textContent='終了しました'; setMouth(false);
}
async function listenerLoop(){
  while(running){
    let d; try { d = await api('current'); } catch(e) { d = null; }
    const s = d?.state || {};
    const item = d?.current?.item || null;
    if (s.status !== 'on_air') {
      nowTalking.textContent='待機中';
      currentText.textContent='@xb_bittensor が配信開始すると、ここで同じ台本を聴けます。';
      await new Promise(r=>setTimeout(r, 3000));
      continue;
    }
    if (item && item.id && item.id !== lastCurrentId) {
      lastCurrentId = item.id;
      log(`listen: ${item.title||''}`);
      await speakText(item.text || bridgeTexts[0], item.title || 'Kurage Radio');
    } else {
      nowTalking.textContent=item?.title ? '配信中: '+item.title : '配信中';
      await new Promise(r=>setTimeout(r, 2000));
    }
  }
  setMouth(false);
}
async function refresh(){ try{ const d=await api('status'); const s=d.state||{}; const q=(d.queue?.items||[]).length; const current=d.current?.item; researchStatus.textContent=`research: ${s.research_status||'idle'} / queue: ${q} / ${s.status||'idle'}`; if(!running && current?.title){ nowTalking.textContent=current.title; currentText.textContent=current.text||''; } }catch(e){} }
setInterval(refresh, 4000); refresh();
if (IS_ADMIN) {
  document.getElementById('startBtn').onclick=async()=>{ const theme=document.getElementById('theme').value.trim(); const hours=Number(document.getElementById('hours').value||1); const d=await api('start',{theme,duration_hours:hours}); endsAt = Date.now()+hours*3600*1000; running=true; log('radio started'); radioLoop(); };
  document.getElementById('interruptBtn').onclick=async()=>{ const theme=document.getElementById('theme').value.trim(); if(!theme){ log('割り込みテーマを入力してください'); return; } await api('interrupt',{theme}); log('theme interrupted: '+theme); };
  document.getElementById('stopBtn').onclick=async()=>{ running=false; speechSynthesis.cancel(); await api('stop'); log('stopped'); nowTalking.textContent='停止中'; setMouth(false); };
  document.getElementById('youtubeStartBtn').onclick=async()=>{ const stream_key=document.getElementById('streamKey').value.trim(); if(!stream_key){ log('YouTube Live ストリームキーを入力してください'); return; } const d=await api('youtube_start',{stream_key,viewer_url:location.href.split('#')[0]}); log(d.ok?'YouTube配信を開始しました':'YouTube配信開始に失敗しました'); };
  document.getElementById('youtubeStopBtn').onclick=async()=>{ const d=await api('youtube_stop',{}); log(d.ok?'YouTube配信を停止しました':'YouTube配信停止に失敗しました'); };
} else {
  document.getElementById('listenBtn').onclick=async()=>{ running=true; log('listening started'); listenerLoop(); };
}
</script>
<?php endif; ?>
</body>
</html>
