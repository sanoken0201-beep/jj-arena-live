import subprocess
from pathlib import Path
from quiz_request_diagnostics import transform_app_js

source=Path('.jj_build/static/app.js').read_text()
assert transform_app_js(source)==source
assert "api('/quiz/question')" not in source
start=source.index('function jjV203DayCheck(){')
end=source.index('\n  window.addEventListener',start)
script='''const assert=require('assert');
let me=null, document={hidden:false}, quiz={q:{date:'2000-01-01'}}, jjV186QuizBusy=false, calls=0;
function jjV186LoadQuiz(){calls++}
'''+source[start:end]+'''
jjV203DayCheck();assert.equal(calls,0);
me={id:1};document.hidden=true;jjV203DayCheck();assert.equal(calls,0);
document.hidden=false;jjV203DayCheck();assert.equal(calls,1);
jjV186QuizBusy=true;jjV203DayCheck();assert.equal(calls,1);
console.log('QUIZ_DAY_GUARD_OK');'''
subprocess.run(['node','-e',script],check=True)
