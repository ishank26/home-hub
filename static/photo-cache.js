/* Only the current 300 normalized photos and thumbnails persist on this device. */
(() => {
  'use strict';
  const LIMIT=256*1024*1024, urls=new Map();
  let database, sample=null, pending=null, clearing=null, epoch=0;
  const downloads=new Set();
  const disabled=()=>{try{return localStorage.getItem('hub.photosDisabled')==='1';}catch{return false;}};
  const key=(id,thumb)=>id+(thumb ? '.thumb' : '');
  function open() {
    if(!database) database=new Promise((resolve,reject)=>{
      const request=indexedDB.open('home-hub-photos',1);
      request.onupgradeneeded=()=>request.result.createObjectStore('sample');
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(new Error('Tablet photo storage unavailable'));
    });
    return database;
  }
  function install(value) {
    for(const url of urls.values())URL.revokeObjectURL(url);
    urls.clear();sample=value;
    for(const item of value.items) {
      urls.set(key(item.id,false),URL.createObjectURL(item.full));
      urls.set(key(item.id,true),URL.createObjectURL(item.thumb));
    }
    return value;
  }
  function valid(value) {
    return value && Array.isArray(value.items) && value.items.length<=300 && value.manifest?.source==='aura' &&
      value.items.every(i=>/^[a-f0-9]{32}$/.test(i.id) && i.full instanceof Blob && i.thumb instanceof Blob && i.full.type==='image/jpeg' && i.thumb.type==='image/jpeg' && i.full.size<=4000000 && i.thumb.size<=500000) &&
      value.items.reduce((n,i)=>n+i.full.size+i.thumb.size,0)<=LIMIT && Array.isArray(value.manifest.photos) && Array.isArray(value.manifest.collections) &&
      value.manifest.photos.length===value.items.length && value.manifest.photos.every((p,i)=>p.id===value.items[i].id);
  }
  async function clear() {
    epoch++;
    try{localStorage.setItem('hub.photosDisabled','1');}catch{/* IDB deletion remains authoritative */}
    for(const controller of downloads)controller.abort();
    for(const url of urls.values())URL.revokeObjectURL(url);
    urls.clear();sample=null;
    const work=(async()=>{
      const db=await open();
      await new Promise((resolve,reject)=>{
        const tx=db.transaction('sample','readwrite');tx.objectStore('sample').delete('current');
        tx.oncomplete=resolve;tx.onerror=tx.onabort=()=>reject(new Error('Tablet photo cleanup unavailable'));
      });
    })();
    clearing=work;
    try{await work;}finally{if(clearing===work)clearing=null;}
  }
  async function load() {
    if(clearing)await clearing;
    if(disabled())return null;
    if(sample)return sample;
    const revision=epoch, db=await open();
    return new Promise((resolve,reject)=>{
      const request=db.transaction('sample').objectStore('sample').get('current');
      request.onsuccess=()=>resolve(revision===epoch && !disabled() && valid(request.result) ? install(request.result) : null);
      request.onerror=()=>reject(new Error('Tablet photo storage unavailable'));
    });
  }
  async function download(id,thumb) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    downloads.add(controller);
    try {
      const response=await fetch('/photos/'+id+(thumb ? '.thumb' : ''),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if(!response.ok || !response.headers.get('content-type')?.startsWith('image/jpeg'))throw new Error('Photo download unavailable');
      const max=thumb ? 500000 : 4000000, reader=response.body.getReader();
      const chunks=[];let size=0;
      try {
        while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>max)throw new Error('Photo too large');chunks.push(part.value);}
      } finally {await reader.cancel().catch(()=>{});}
      return new Blob(chunks,{type:'image/jpeg'});
    } finally {clearTimeout(timer);downloads.delete(controller);}
  }
  async function sync(manifest) {
    if(manifest.source==='aura' && Array.isArray(manifest.photos) && !manifest.photos.length){await clear();return null;}
    if(pending)return pending;
    const revision=epoch;
    pending=(async()=>{
      if(manifest.source!=='aura' || !Array.isArray(manifest.photos))return null;
      const photos=manifest.photos.slice(0,300);
      if(!photos.every(p=>/^[a-f0-9]{32}$/.test(p.id)) || new Set(photos.map(p=>p.id)).size!==photos.length)throw new Error('Invalid photo sample');
      const old=await load();
      if(old && old.manifest.syncedAt===manifest.syncedAt && old.items.map(i=>i.id).join()===photos.map(p=>p.id).join())return old;
      const items=[];let bytes=0;
      for(const photo of photos) {
        const full=await download(photo.id,false),thumb=await download(photo.id,true);
        bytes+=full.size+thumb.size;if(bytes>LIMIT)throw new Error('Tablet photo sample exceeds 256 MB');
        items.push({id:photo.id,full,thumb});
      }
      const value={manifest:{...manifest,photos},items,bytes,storedAt:Date.now()};
      const db=await open();
      if(revision!==epoch)throw new Error('Photo sync canceled');
      await new Promise((resolve,reject)=>{
        const transaction=db.transaction('sample','readwrite');
        transaction.objectStore('sample').put(value,'current');
        transaction.oncomplete=resolve;transaction.onerror=transaction.onabort=()=>reject(new Error('Tablet photo sample could not be saved'));
      });
      if(revision!==epoch)throw new Error('Photo sync canceled');
      try{localStorage.removeItem('hub.photosDisabled');}catch{/* IDB saved successfully */}
      return install(value);
    })();
    try{return await pending;}finally{pending=null;}
  }
  window.HubPhotoCache={load,sync,clear,url:(id,thumb)=>urls.get(key(id,thumb)),hasURL:value=>[...urls.values()].includes(value),info:()=>sample ? {count:sample.items.length,bytes:sample.bytes,storedAt:sample.storedAt} : null};
})();
