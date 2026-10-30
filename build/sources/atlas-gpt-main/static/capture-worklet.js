class Capture extends AudioWorkletProcessor {
  constructor(){super();this.buffer=new Int16Array(1024);this.offset=0;}
  process(inputs){
    const channel=inputs[0]?.[0];
    if(channel)for(let i=0;i<channel.length;i++){
      this.buffer[this.offset++]=Math.max(-1,Math.min(1,channel[i]))*32767;
      if(this.offset===1024){this.port.postMessage(this.buffer.buffer,[this.buffer.buffer]);this.buffer=new Int16Array(1024);this.offset=0;}
    }
    return true;
  }
}
registerProcessor('atlas-capture',Capture);
