/* Keep an unresolved point operation across network errors and page reloads. */
(function(root){
  function pointRequests(storage, actorId, newId){
    const key='jj-admin-points-pending-v1:'+actorId;
    return {
      pending(){return JSON.parse(storage.getItem(key)||'null')},
      prepare(body){
        const prior=this.pending();
        if(prior){
          const {request_id,...original}=prior;
          if(JSON.stringify(original)!==JSON.stringify(body))throw new Error('前回の処理結果が未確認です。復元された内容のまま再送して確認してください。');
          return prior;
        }
        const request={...body,request_id:newId()};
        // Fail before sending if persistence is unavailable.
        storage.setItem(key,JSON.stringify(request));
        return request;
      },
      complete(){storage.removeItem(key)}
    };
  }
  if(typeof module!=='undefined')module.exports=pointRequests;
  else root.jjPointRequests=pointRequests;
})(typeof window==='undefined'?{}:window);
