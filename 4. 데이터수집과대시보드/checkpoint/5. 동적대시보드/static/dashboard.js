'use strict';
let DATA=[], regionNames=[], periods={};
const $=id=>document.getElementById(id), fmt=(v,d=2)=>v===null||!Number.isFinite(v)?'자료 부족':v.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d});
const products=['실내등유','보통휘발유','자동차용경유','고급휘발유','자동차용부탄'];
products.forEach(x=>$('product').add(new Option(x,x)));
function observations(kind,category,period){return DATA.filter(r=>r.kind===kind&&r.product===$('product').value&&(kind==='national'||r.category===category)&&(!period||r.period===period));}
function average(kind,category,period){const rows=observations(kind,category,period).filter(r=>Number.isFinite(r.price)&&r.price>0);return new Set(rows.map(r=>r.date)).size===7?rows.reduce((a,r)=>a+r.price,0)/7:null;}
function stats(kind,category){let recent=average(kind,category,'recent'),previous=average(kind,category,'previous');return {recent,previous,delta:recent!==null&&previous!==null?recent-previous:null};}
function signed(n){return n===null?'자료 부족':(n>0?'+':n<0?'−':'')+fmt(Math.abs(n));}
function changeClass(n){return n>0?'up':n<0?'down':'';}
function setChange(id,n,unit='원/L'){const el=$(id);el.className='metric-value '+changeClass(n);el.textContent=signed(n);if(n!==null){const s=document.createElement('small');s.textContent=unit;el.append(s);}}
function usage(){const value=$('liters').valueAsNumber;return Number.isFinite(value)?Math.max(0,Math.min(10000,value)):0;}
function updateBill(){const s=stats('region',$('region').value),l=usage(),cost=s.recent===null?null:s.recent*l,diff=s.delta===null?null:s.delta*l;$('bill').textContent=fmt(cost,0)+(cost===null?'':' 원');$('cardBill').textContent=fmt(cost,0)+(cost===null?'':'원');$('cardBillNote').textContent=`월 ${fmt(l,0)}L 사용 가정 · 지역 평균 기준`;$('billChange').className='bill-change '+changeClass(diff);$('billChange').textContent=diff===null?'직전 대비: 자료 부족':`직전 가격 적용 시보다 ${fmt(Math.abs(diff),0)}원 ${diff>0?'증가':diff<0?'감소':'변동 없음'}`;$('scenario').textContent=fmt(l*50,0)+'원';}
function renderChart(){const region=$('region').value,local=observations('region',region),national=observations('national','전국'),dates=[...new Set(DATA.map(r=>r.date))].sort(),series=[local,national],values=series.flat().filter(r=>r.price>0).map(r=>r.price);if(!values.length){$('chart').innerHTML='<div class="empty">해당 유종의 가격 자료가 없습니다.</div>';return;}
 const W=720,H=245,L=60,R=15,T=26,B=30,spread=Math.max(...values)-Math.min(...values),pad=Math.max(spread*.18,1),lo=Math.min(...values)-pad,hi=Math.max(...values)+pad,x=i=>L+i*(W-L-R)/13,y=v=>T+(hi-v)/(hi-lo)*(H-T-B),boundary=(x(6)+x(7))/2;
 let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${region}과 전국의 14일 일평균 가격 추이. 세로축은 가격 차이 확인을 위해 확대했습니다."><rect x="${boundary}" y="12" width="${W-R-boundary}" height="${H-B-12}" fill="#f2f6ed"/><text x="${boundary+12}" y="24" fill="#829078" font-size="10">최근 7일</text>`;
 for(let i=0;i<4;i++){let v=lo+(hi-lo)*i/3,yy=y(v);svg+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#e9ede4" stroke-dasharray="3 4"/><text x="${L-10}" y="${yy+4}" text-anchor="end" font-size="10" fill="#8b9587">${fmt(v,1)}</text>`;}
 svg+='<text x="10" y="12" font-size="10" fill="#8b9587">원/L</text>';
 for(const [s,color,dashed] of [[national,'#a7b4a8',true],[local,'#177250',false]]){const map=new Map(s.filter(r=>r.price>0).map(r=>[r.date,r]));let path='',active=false;dates.forEach((date,i)=>{const r=map.get(date);if(!r){active=false;return;}path+=`${active?'L':'M'}${x(i)},${y(r.price)} `;active=true;});svg+=`<path d="${path}" fill="none" stroke="${color}" stroke-width="${dashed?2:3}" ${dashed?'stroke-dasharray="5 5"':''}/>`;dates.forEach((date,i)=>{const r=map.get(date);if(r)svg+=`<circle cx="${x(i)}" cy="${y(r.price)}" r="${dashed?2:3.5}" fill="${color}"><title>${date} · ${dashed?'전국':region}: ${fmt(r.price)}원/L</title></circle>`;});}
 dates.forEach((d,i)=>{if(i%2===0||i===13)svg+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle" font-size="10" fill="#8b9587">${d.slice(5).replace('-','.')}</text>`;});$('chart').innerHTML=svg+'</svg>';
}
function renderRanking(){const rows=regionNames.map(name=>({name,...stats('region',name)})),valid=rows.filter(r=>r.recent!==null);valid.sort($('sort').value==='delta'?(a,b)=>(b.delta??-Infinity)-(a.delta??-Infinity):(a,b)=>a.recent-b.recent);$('ranking').replaceChildren();const max=Math.max(...valid.map(r=>r.recent));for(const [i,r] of valid.entries()){const b=document.createElement('button');b.className='rank-row'+(r.name===$('region').value?' selected':'');b.setAttribute('aria-label',`${r.name}, 평균 ${fmt(r.recent)}원, 선택`);b.innerHTML=`<span class="rank-no">${String(i+1).padStart(2,'0')}</span><span class="name">${r.name}</span><span class="track"><span class="fill" style="display:block;width:${r.recent/max*100}%"></span></span><span class="rank-price">${fmt(r.recent)}</span><span class="rank-delta ${changeClass(r.delta)}">${signed(r.delta)}</span>`;b.onclick=()=>{$('region').value=r.name;render();};$('ranking').append(b);}if(!valid.length)$('ranking').innerHTML='<div class="empty">7일 관측이 충족된 지역이 없습니다.</div>';const missing=rows.length-valid.length;if(missing){const p=document.createElement('p');p.className='footnote';p.textContent=`자료 부족으로 ${missing}개 지역을 제외했습니다.`;$('ranking').append(p);}}
function renderBrands(){const names=[...new Set(DATA.filter(r=>r.kind==='brand').map(r=>r.category))],rows=names.map(name=>({name,...stats('brand',name)})).filter(r=>r.recent!==null).sort((a,b)=>a.recent-b.recent),nat=stats('national','전국').recent;$('brandList').replaceChildren();for(const r of rows){const el=document.createElement('div');el.className='brand-row';el.innerHTML=`<div>${r.name}<small>전국 평균 대비 ${nat===null?'자료 부족':signed(r.recent-nat)+'원/L'}</small></div><div class="right"><b>${fmt(r.recent)}</b><div class="change ${changeClass(r.delta)}">직전 대비 ${signed(r.delta)}</div></div>`;$('brandList').append(el);}if(!rows.length)$('brandList').innerHTML='<div class="empty">해당 유종의 상표별 자료가 없습니다.</div>';}
function render(){const region=$('region').value,product=$('product').value,s=stats('region',region),n=stats('national','전국');$('localLabel').textContent=region+' · '+product;$('localPrice').textContent=fmt(s.recent);setChange('delta',s.delta);$('deltaNote').textContent=s.delta===null?'직전 또는 최근 7일 관측 부족':`직전 ${fmt(s.previous)}원/L · ${s.delta>0?'+':''}${fmt(s.delta/s.previous*100)}%`;const gap=s.recent!==null&&n.recent!==null?s.recent-n.recent:null;setChange('gap',gap);$('nationalNote').textContent=`전국 최근 평균 ${fmt(n.recent)}원/L`;$('trendCaption').textContent=product+' · '+periods.previous.start+' — '+periods.recent.end+' · 세로축 확대 표시';$('legendRegion').textContent=region;let text=gap===null?'이 지역·유종은 7일 관측 자료가 부족합니다.':`${region}의 ${product} 최근 평균은 전국보다 ${fmt(Math.abs(gap))}원/L ${gap>0?'높습니다':gap<0?'낮습니다':'차이가 없습니다'}.`;if(s.delta!==null)text+=` 직전 7일 대비 ${fmt(Math.abs(s.delta))}원/L ${s.delta>0?'상승':s.delta<0?'하락':'보합'}했습니다.`;$('insight').textContent=text;renderChart();renderRanking();renderBrands();updateBill();}
$('region').onchange=render;$('product').onchange=render;$('sort').onchange=renderRanking;
$('liters').oninput=()=>{$('slider').value=Math.min(1000,usage());updateBill();};$('liters').onchange=()=>{$('liters').value=usage();updateBill();};$('slider').oninput=()=>{$('liters').value=$('slider').value;updateBill();};
$('download').onclick=()=>{const rows=[['지역','유종','직전 평균(원/L)','최근 평균(원/L)','증감(원/L)','직전 기간','최근 기간'],...regionNames.map(name=>{const s=stats('region',name);return [name,$('product').value,s.previous??'',s.recent??'',s.delta??'',periods.previous.start+'~'+periods.previous.end,periods.recent.start+'~'+periods.recent.end];})];const csv='\ufeff'+rows.map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='지역별_'+$('product').value+'_기간비교.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};

let timer;
function schedule(delay){clearTimeout(timer);timer=setTimeout(load,delay);}
async function load(){
  let delay=60000;
  try {
    const response=await fetch('/api/dashboard',{cache:'no-store'});
    if(!response.ok) throw new Error('서버에 연결하지 못했습니다.');
    const {data,meta,mail}=await response.json();
    if(data){
      DATA=data.records;periods=data.periods;
      const selection=$('region').value || '서울';
      regionNames=[...new Set(DATA.filter(r=>r.kind==='region').map(r=>r.category))].sort((a,b)=>a.localeCompare(b,'ko'));
      $('region').replaceChildren(...regionNames.map(x=>new Option(x,x)));
      $('region').value=regionNames.includes(selection)?selection:regionNames[0];
      $('periodInfo').textContent=`최근 ${periods.recent.start} ~ ${periods.recent.end} / 직전 ${periods.previous.start} ~ ${periods.previous.end} · 각 7일 평균`;
      $('previousPeriod').textContent=`직전 7일 ${periods.previous.start} ~ ${periods.previous.end}`;
      $('recentPeriod').textContent=`최근 7일 ${periods.recent.start} ~ ${periods.recent.end}`;
      $('dataScope').textContent=`자료 기준일 ${data.as_of} · 수집 ${new Date(data.collected_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}`;
      document.querySelectorAll('#region,#product,#sort,#liters,#slider,#download').forEach(el=>el.disabled=false);
      render();
      loadBriefing();
      updateMailContext(mail);
    }
    let message=meta.refreshing?'최신 자료 갱신 중…':meta.error?meta.error:data?'저장된 최신 자료 사용 중':'자료 수집 대기 중';
    if(meta.stale&&data) message+=' · 이전 자료 표시';
    if(meta.retry_at) message+=` · 재시도 예정 ${new Date(meta.retry_at).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'})}`;
    $('connectionStatus').textContent=message;
    if(meta.refreshing) delay=2000;
  }catch(error){$('connectionStatus').textContent='서버 연결을 확인하세요. 1분 후 자동으로 다시 연결합니다.';}
  finally{schedule(delay);}
}
document.querySelectorAll('#region,#product,#sort,#liters,#slider,#download').forEach(el=>el.disabled=true);
document.addEventListener('visibilitychange',()=>{if(!document.hidden) load();});
load();

let briefingTimer, briefingLoading=false;
async function loadBriefing(){
  if(briefingLoading) return;
  briefingLoading=true;
  clearTimeout(briefingTimer);
  try{
    const response=await fetch('/api/briefing',{cache:'no-store'});
    if(!response.ok) throw new Error('브리핑 조회 실패');
    const result=await response.json();
    $('briefingText').textContent=result.text;
    const labels={openai:'AI 생성 · GPT-6 Luna',preview:'미리 작성한 브리핑',calculated:'데이터 기반 요약',pending:'자료 확인 중'};
    $('briefingBadge').textContent=labels[result.source]||'유가 요약';
    let note='전국 평균 기준 · 지역·유종 선택과 별개로 전체 흐름을 요약합니다.';
    if(result.source==='preview') note+=' 현재 문구는 API 호출 없이 작성한 미리보기입니다.';
    if(result.as_of) note+=` 자료 기준일 ${result.as_of}.`;
    if(result.refreshing){note+=' AI 브리핑 생성 중…';briefingTimer=setTimeout(loadBriefing,2000);}
    if(result.error) note+=' '+result.error;
    $('briefingNote').textContent=note;
  }catch(error){$('briefingNote').textContent='브리핑을 불러오지 못했습니다. 잠시 후 자동으로 다시 확인합니다.';}
  finally{briefingLoading=false;}
}

let mailContext=null, mailBusy=false, autoSubject='', draftSnapshot=null;
let sendSignature='', sendRequestId='', lastSentSignature='';
function mailStatus(text,error=false){$('mailStatus').textContent=text;$('mailStatus').className='mail-status'+(error?' error':'');}
function mailControls(busy){
  mailBusy=busy;
  for(const id of ['mailDraft','mailSend']) $(id).disabled=busy||!mailContext;
  for(const id of ['mailRecipient','mailSubject','mailBody']) $(id).disabled=busy;
}
function updateMailContext(context){
  if(!context) return;
  if(!$('mailSubject').value||$('mailSubject').value===autoSubject) $('mailSubject').value=context.subject;
  autoSubject=context.subject;
  if(draftSnapshot&&draftSnapshot!==context.snapshot_id) mailStatus('자료가 갱신되었습니다. 본문의 비교 기간을 확인하고 초안을 다시 작성해주세요.',true);
  mailContext=context;
  $('mailAttachment').textContent=context.attachment;
  $('mailAttachment').href='/api/mail/attachment/'+context.snapshot_id;
  $('mailPeriod').textContent=`기준일 ${context.as_of} · 최근 ${context.periods.recent.start} ~ ${context.periods.recent.end}`;
  mailControls(mailBusy);
}
async function mailPost(path,payload){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Dashboard-Request':'1'},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'입력 내용과 연결 상태를 확인해주세요.');
  return result;
}
$('mailDraft').onclick=async()=>{
  if(!mailContext||mailBusy) return;
  const snapshot=mailContext.snapshot_id;
  mailControls(true);mailStatus('데이터를 바탕으로 메일 초안을 작성하고 있습니다…');
  try{
    const result=await mailPost('/api/mail/draft',{snapshot_id:snapshot});
    if(mailContext.snapshot_id!==result.snapshot_id) throw new Error('자료가 갱신되었습니다. 초안을 다시 작성해주세요.');
    $('mailSubject').value=result.subject;autoSubject=result.subject;
    $('mailBody').value=result.body;draftSnapshot=result.snapshot_id;
    mailStatus(result.source==='openai'?'AI 초안을 작성했습니다. 내용을 검토·수정한 후 전송해주세요.':'OpenAI API 키가 없어 데이터 기반 기본 초안을 작성했습니다. 검토 후 전송할 수 있습니다.');
  }catch(error){mailStatus(error.message||'초안을 작성하지 못했습니다.',true);}
  finally{mailControls(false);}
};
$('mailSend').onclick=async()=>{
  if(!mailContext||mailBusy) return;
  const recipient=$('mailRecipient'), subject=$('mailSubject').value.trim(), body=$('mailBody').value;
  if(!recipient.value.trim()||!recipient.checkValidity()){recipient.reportValidity();mailStatus('올바른 받는 이메일 주소를 입력해주세요.',true);return;}
  if(!subject||!body.trim()){mailStatus('메일 제목과 내용을 입력해주세요.',true);return;}
  if(draftSnapshot&&draftSnapshot!==mailContext.snapshot_id){mailStatus('자료가 갱신되었습니다. 초안을 다시 작성하고 내용을 확인해주세요.',true);return;}
  const payload={snapshot_id:mailContext.snapshot_id,recipient:recipient.value.trim(),subject,body};
  const signature=JSON.stringify(payload);
  if(signature===lastSentSignature){mailStatus('같은 내용의 메일을 이미 전송했습니다. 보낸메일함을 확인해주세요.');return;}
  if(signature!==sendSignature){sendSignature=signature;sendRequestId=crypto.randomUUID();}
  payload.request_id=sendRequestId;
  mailControls(true);mailStatus('엑셀을 준비하고 메일을 전송하고 있습니다…');
  try{
    const result=await mailPost('/api/mail/send',payload);
    lastSentSignature=signature;mailStatus(result.message);
  }catch(error){mailStatus(error.message||'연결이 끊겼습니다. 다시 전송하기 전에 보낸메일함을 확인하세요.',true);}
  finally{mailControls(false);}
};
