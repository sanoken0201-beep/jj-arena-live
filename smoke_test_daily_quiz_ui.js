'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8').replace(/\r\n/g,'\n');
new vm.Script(source);
const from=source.indexOf('// v1.20.3 daily poker quiz v2.');
assert(from>=0);
const addon=source.slice(from,source.lastIndexOf('})();'));
assert(addon.includes('v1.24.3 focused non-poker product UX'), 'Final v1.24.3 renderer must be included');
assert(!addon.includes('data-quiz="'), 'Legacy handler coerces string answers to Number');
const nodes=new Map(['#quizStage','#quizChoices','#quizScore'].map(k=>[k,{innerHTML:'',textContent:''}]));
const events={}, state={calls:0,posts:[],fail:false};
const addListener=(name,fn)=>{(events[name]??=[]).push(fn)};
const dispatch=(name,event)=>{for(const fn of events[name]||[])fn(event)};
const progress={answered:0,correct:0,earned:0,remaining:10,total:10,max_daily_reward:100};
state.q={id:'test-question',date:'2000-01-01',slot:1,category_label:'Range',prompt:'考える問題',reward:10,choices:[{value:'opaque-choice',label:'回答'}],progress};
const context=vm.createContext({
  Intl,Date,quiz:{},jjV186QuizBusy:false,jjV186LoadQuiz:null,renderQuiz:null,answerQuiz:null,
  $:s=>nodes.get(s),safe:s=>String(s),fmt:v=>String(Number(v??0)),toast:()=>{},setInterval:()=>{},setTimeout:()=>{},
  window:{addEventListener:()=>{}},
  document:{hidden:false,querySelectorAll:()=>[],addEventListener:addListener},
  api:async()=>{state.calls++;if(state.fail)throw Error('offline');return state.q},
  post:async(path,body)=>{state.posts.push(body);return {correct:false,awarded:10,correct_label:'正解',explanation:'理由を確認',progress:{...progress,answered:1,earned:10,remaining:9}}}
});
vm.runInContext(addon,context);
(async()=>{
  await context.jjV186LoadQuiz();
  const choices=nodes.get('#quizChoices').innerHTML;
  const stage=nodes.get('#quizStage').innerHTML;
  assert(choices.includes('data-daily-answer="opaque-choice"'));
  assert(choices.includes('<span>A</span>'));
  assert(stage.includes('DAILY QUIZ'));
  assert(stage.includes('問題 1 / 10'));
  assert(stage.includes('今日 +0pt'));

  dispatch('click',{target:{closest:s=>s==='[data-daily-answer]'?{dataset:{dailyAnswer:'opaque-choice'}}:null}});
  await new Promise(setImmediate);
  assert.equal(state.posts[0].answer,'opaque-choice');
  const result=nodes.get('#quizStage').innerHTML;
  assert(result.includes('理由を確認'));
  assert(result.includes('あなたの回答'));
  assert(result.includes('正解'));
  assert(result.includes('今日合計 <b>+10pt</b>'));
  assert(nodes.get('#quizChoices').innerHTML.includes('次の問題へ'));

  await context.answerQuiz('opaque-choice');
  assert.equal(state.posts.length,1,'Answered question must not be submitted twice');
  state.fail=true;
  await context.jjV203NextQuiz();
  assert(context.quiz.lastResult, 'Failed next request must preserve explanation');
  state.fail=false;
  state.q={done:true,date:'2000-01-01',progress:{...progress,answered:10,correct:7,earned:100,remaining:0}};
  await context.jjV203NextQuiz();
  assert(nodes.get('#quizStage').innerHTML.includes('DAILY COMPLETE'));
  assert(nodes.get('#quizStage').innerHTML.includes('7 / 10 正解'));
  assert.equal(nodes.get('#quizChoices').innerHTML,'');
  const before=state.calls;
  context.jjV203DayCheck();
  await new Promise(setImmediate);
  assert.equal(state.calls,before+1,'Open tab must refresh after JST rollover');
  console.log('JJ_DAILY_QUIZ_UI_OK');
})().catch(e=>{console.error(e);process.exitCode=1});