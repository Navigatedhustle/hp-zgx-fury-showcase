"""Local original soundtrack and FFmpeg cuts. No downloaded music or cloud calls."""
import subprocess
import textwrap
import time
import wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from imageio_ffmpeg import get_ffmpeg_exe

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def title_card(path,text,index):
    image=Image.new('RGB',(1280,704),'#06101e');draw=ImageDraw.Draw(image)
    draw.line((120,220,1160,220),fill='#177ea7',width=2)
    draw.text((120,166),'FURY ORIGINAL / '+('THE MISSION' if index==0 else 'THE NEXT CHAPTER'),font=ImageFont.truetype(FONT,20),fill='#73d9ed')
    lines=textwrap.wrap(text.upper(),24)
    for row,line in enumerate(lines[:3]):draw.text((120,270+row*76),line,font=ImageFont.truetype(FONT,56),fill='#edf8ff')
    draw.text((120,580),'CREATED LOCALLY. STARRING YOU.',font=ImageFont.truetype(FONT,18),fill='#9aabbc')
    image.save(path);image.close()


def soundtrack(path,duration):
    rate=24000;t=np.arange(round(duration*rate))/rate
    # Original procedural bass/swell bed: oscillators and envelope, no samples.
    frequencies=np.array([55,65.406,73.416])
    section=np.minimum((t/(duration/3)).astype(int),2);base=frequencies[section]
    phase=2*np.pi*np.cumsum(base)/rate
    swell=np.sin(np.pi*np.minimum(t/duration,1))**.7
    pulse=(.6+.4*np.sin(2*np.pi*.5*t))
    left=(.12*np.sin(phase)+.055*np.sin(phase*1.5)+.035*np.sin(phase*2))*swell*pulse
    right=(.12*np.sin(phase+.04)+.055*np.sin(phase*1.5+.2)+.035*np.sin(phase*2+.3))*swell*pulse
    data=(np.clip(np.column_stack((left,right)),-1,1)*32767).astype('<i2')
    with wave.open(str(path),'wb') as output:output.setnchannels(2);output.setsampwidth(2);output.setframerate(rate);output.writeframes(data.tobytes())


def assemble(folder,shots,titles,deleted):
    folder=Path(folder)
    if deleted() or not folder.is_dir():raise InterruptedError('Session deleted')
    clip_duration=98/24 if shots==3 else 121/24
    duration=2+shots*clip_duration
    for index,title in enumerate(titles):title_card(folder/f'title-{index}.png',title,index)
    watermark=Image.new('RGBA',(370,40),(3,10,18,180));draw=ImageDraw.Draw(watermark)
    draw.text((10,10),'AI generated on HP ZGX Fury',font=ImageFont.truetype(FONT,20),fill='white');watermark.save(folder/'watermark.png');watermark.close()
    soundtrack(folder/'soundtrack.wav',duration)
    command=[get_ffmpeg_exe(),'-v','error','-y','-threads','4','-filter_complex_threads','1']
    inputs=[(folder/'title-0.png',1),*[(folder/f'clip-{i}.mp4',clip_duration) for i in range(shots)],(folder/'title-1.png',1)]
    for path,_ in inputs:
        if path.suffix=='.png':command+=['-loop','1','-framerate','24']
        command+=['-i',str(path)]
    narration_index=len(inputs);music_index=narration_index+1;mark_index=music_index+1
    command+=['-f','s16le','-ar','24000','-ac','1','-i',str(folder/'narration.pcm'),'-i',str(folder/'soundtrack.wav'),'-loop','1','-i',str(folder/'watermark.png')]
    filters=[]
    for index,(_,seconds) in enumerate(inputs):filters.append(f'[{index}:v]scale=1280:704:force_original_aspect_ratio=increase,crop=1280:704,setsar=1,fps=24,trim=duration={seconds},setpts=PTS-STARTPTS[v{index}]')
    filters.append(''.join(f'[v{i}]' for i in range(len(inputs)))+f'concat=n={len(inputs)}:v=1:a=0[cut]')
    filters.append(f'[cut][{mark_index}:v]overlay=main_w-overlay_w-24:main_h-overlay_h-18:format=auto[outv]')
    filters.append(f'[{narration_index}:a]adelay=1000,apad,atrim=duration={duration},volume=1.15[voice]')
    filters.append(f'[{music_index}:a]afade=t=in:d=1,afade=t=out:st={duration-1}:d=1,volume=.7[bed]')
    filters.append('[voice][bed]amix=inputs=2:normalize=0,alimiter=limit=.95[a]')
    command+=['-filter_complex',';'.join(filters),'-map','[outv]','-map','[a]','-t',str(duration),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-threads','4','-c:a','aac','-b:a','160k','-ac','2','-movflags','+faststart',str(folder/'trailer.mp4')]
    process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        while process.poll() is None:
            if deleted():
                process.terminate();process.wait(timeout=10);raise InterruptedError('Session deleted; final cut discarded')
            time.sleep(.2)
        error=process.stderr.read()
        if process.returncode:raise RuntimeError('Local final-cut encoding failed')
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)
