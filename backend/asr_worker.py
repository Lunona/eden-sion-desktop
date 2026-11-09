"""On-demand CPU-only ASR worker. The host owns and removes every input file."""
import json,sys,time
from pathlib import Path
import numpy as np
import av
from faster_whisper import WhisperModel

def decode(path):
    # The existing environment has an older PyAV without metadata_errors.
    # Decode locally instead of changing the shared GPT-SoVITS environment.
    output=[];size=0;resampler=av.AudioResampler(format='s16',layout='mono',rate=16000)
    with av.open(str(path),mode='r') as container:
        for frame in container.decode(audio=0):
            frame.pts=None
            frames=resampler.resample(frame)
            if not isinstance(frames,list):frames=[frames] if frames else []
            for part in frames:
                samples=part.to_ndarray().reshape(-1);size+=len(samples)
                if size>32*16000:raise ValueError('audio too long')
                output.append(samples)
        frames=resampler.resample(None)
        if not isinstance(frames,list):frames=[frames] if frames else []
        output.extend(part.to_ndarray().reshape(-1) for part in frames)
    return np.concatenate(output).astype(np.float32)/32768 if output else np.zeros(0,dtype=np.float32)

model=None
for line in sys.stdin:
    request={}
    try:
        request=json.loads(line);start=time.monotonic()
        if model is None:model=WhisperModel(sys.argv[1],device='cpu',compute_type='int8',cpu_threads=4,num_workers=1,local_files_only=True)
        if request.get('warmup') is True:continue
        audio=Path(request['file'])
        if not audio.is_file() or audio.stat().st_size>8*1024*1024:raise ValueError('invalid audio')
        language=request.get('language')
        if language not in ('zh','ja','en',None):raise ValueError('invalid language')
        segments,info=model.transcribe(decode(audio),language=language,beam_size=1,best_of=1,vad_filter=True,condition_on_previous_text=False)
        if info.duration>32:raise ValueError('audio too long')
        text=''.join(s.text for s in segments).strip()
        result={'id':request['id'],'text':text[:4000],'language':info.language,'milliseconds':round((time.monotonic()-start)*1000)}
    except Exception as error:
        import traceback
        traceback.print_exc(file=sys.stderr)
        result={'id':request.get('id') if isinstance(request,dict) else None,'error':type(error).__name__}
    print(json.dumps(result,ensure_ascii=False),flush=True)
