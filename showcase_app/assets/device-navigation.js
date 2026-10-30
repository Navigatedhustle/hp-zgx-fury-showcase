/* Keep cross-app links on the device the browser actually connected to. */
(() => {
 if(!location.hostname.endsWith('.ts.net'))return;
 const ports={'8080':'','8200':'8200','8501':'8501','8765':'8765','8800':'8800'};
 function rewrite(anchor){try{const url=new URL(anchor.getAttribute('href'),location.href);if(!['localhost','127.0.0.1'].includes(url.hostname)||!(url.port in ports))return;url.protocol='https:';url.hostname=location.hostname;url.port=ports[url.port];anchor.href=url.href;}catch{}}
 function scan(root){if(root.nodeType!==1)return;if(root.matches('a[href]'))rewrite(root);root.querySelectorAll('a[href]').forEach(rewrite);}
 function start(){scan(document.documentElement);new MutationObserver(records=>{for(const r of records)for(const node of r.addedNodes)scan(node);}).observe(document.body,{childList:true,subtree:true});}
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',start):start();
})();
