'use strict';

class VoiceRunway {
  constructor(startedAt) {
    this.startedAt=startedAt;
  }

  reserve(now) {
    return Math.min(8,Math.max(4,(now-this.startedAt)/1000+.5));
  }

  readyEarly(now, audioSeconds) {
    if(this.finished)return false;
    if(audioSeconds>=4){this.finished=true;return false;}
    this.firstAt??=now;
    const elapsed=(now-this.startedAt)/1000;
    const sinceFirst=(now-this.firstAt)/1000;
    // A single burst can be several HTTP reads. Wait for sustained delivery.
    if(audioSeconds<2.8||sinceFirst<.55||audioSeconds<elapsed*2.4)return false;
    this.finished=true;
    return true;
  }
}

module.exports={VoiceRunway};
