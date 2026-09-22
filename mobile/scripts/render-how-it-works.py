"""Create the captioned H.264 walkthrough from local-preview screenshots.

Run capture-how-it-works.mjs first. Requires Pillow and imageio-ffmpeg.
No remote images, accounts, provider calls or production data are used.
"""
from pathlib import Path
import json
import math
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

MOBILE = Path(__file__).resolve().parents[1]
INPUT = MOBILE / 'artifacts/how-it-works'
OUTPUT = MOBILE / 'public/media'
OUTPUT.mkdir(parents=True, exist_ok=True)
W, H, FPS = 1600, 900, 15
BG, CARD, TEXT, MUTED = '#141020', '#241D3C', '#FFFFFF', '#C9C2DC'
MINT, LILAC, CORAL = '#3DDC97', '#A78BFA', '#FF4D6D'
FONT = Path('C:/Windows/Fonts/segoeui.ttf')
BOLD = Path('C:/Windows/Fonts/segoeuib.ttf')
def font(size, bold=False): return ImageFont.truetype(str(BOLD if bold else FONT), size)

# Each screen is captured from the real shared mobile UI, using mock data.
SCENES = [
 ('01-signup','Start with your invited number','SIGN UP OR LOG IN',
  'Choose Sign up to review a prefilled profile. Choose Log in to go straight to Dashboard. Both require your own OTP.', 'Before the timed test'),
 ('02-vision','1 / Vision','WHERE YOU ARE HEADED',
  'Review your existing pillars and choices. Use Add detail or Declare a change when available, then continue to Stats.', 'Save edits before continuing'),
 ('03-stats','2 / Stats','ALREADY FILLED IN',
  'Check your details and edit what has changed. Save changes. Editing a verified field may reopen its verification.', 'Your existing profile is reused'),
 ('04-chemistry','3 / Chemistry','WHAT YOU WOULD DO TOGETHER',
  'Review your activity choices. Save chemistry, then Finish sign up. No need to type your profile from scratch.', 'Your choices remain yours'),
 ('05-home','Your Home, your next step','DASHBOARD',
  'NEXT FOR YOU points to your next action. How it works stays near the top whenever you want a reminder.', 'Shared Android + iOS experience'),
 ('06-reach','Set your REACH filters','REALITY CHECK',
  'Review your preferences before the matches open. Matching works in both directions: each person must fit the other.', '0 min → Monday 10:00'),
 ('07-match1','Match 1 opens','EXPRESS YOUR KEENNESS',
  'Open Week and review your first match. Express interest or Pass. A mutual choice is needed before planning together.', '3 min → Monday 12:00'),
 ('08-match2','M1 closes. Match 2 opens.','UP TO THREE MATCHES',
  'If you have not locked in, review Match 2. Your previous window closes as the next match opens.', '6 min → Tuesday 12:00'),
 ('09-match3','M2 closes. Match 3 opens.','THE LAST MATCH OF THE WEEK',
  'Review Match 3 if you are still searching. M3 closes Wednesday at 18:00, when the Slots checkpoint begins.', '9 min → Wednesday 12:00'),
 ('10-slots','Share your weekend Slots','CALENDAR',
  'After mutual lock-in, both complete alignment and availability. Breakfast 09:00, Lunch 13:00, Coffee 17:00, Dinner 19:30.', '12 min → Wednesday 18:00'),
 ('11-overlap','Choose a time you both offered','OVERLAP / PLAN SELECTION',
  'Save availability and select a real overlapping slot. Both partners must complete alignment before a plan can be created.', '15 min → Thursday 12:00'),
 ('12-plan','Review your date plan','YOUR SELECTED TIME AND PLACE',
  'Check the plan together. At minute 21, the shared clock jumps to the latest saved weekend date, rounded up if needed.', '21 min → selected date start'),
 ('13-agreement','Complete the agreement together','READ. ACKNOWLEDGE. SIGN.',
  'Review the rules and make your own acknowledgements. Both partners must complete their steps. Beta face checks are simulated.', '18 min → Thursday 18:00'),
 ('14-debrief','After the date: Debrief','FLAGS AND YOUR DECISION',
  'Share your flags, then decide what comes next. RC opens at Sunday 21:00 only if your lock-in has ended.', '24 min → Debrief · 27 min → RC'),
]
# Put agreement before the selected-date explanation in playback.
SCENES[11], SCENES[12] = SCENES[12], SCENES[11]

ROWS = [
 ('0','Monday 10:00','REACH / Reality Check'),
 ('3','Monday 12:00','Match 1 opens'),
 ('6','Tuesday 12:00','M1 closes · Match 2 opens'),
 ('9','Wednesday 12:00','M2 closes · Match 3 opens'),
 ('12','Wednesday 18:00','M3 closes · weekend Slots'),
 ('15','Thursday 12:00','Overlap / plan selection'),
 ('18','Thursday 18:00','Review and complete the agreement'),
 ('21','Selected date start*','Rounded up to the next whole hour'),
 ('24','Debrief opening*','Flags and your decision'),
 ('27','Sunday 21:00','RC if your lock-in has ended'),
 ('30','Next Monday 12:00','Cross RC close at 11:00 · next cycle'),
]

def wrap(draw, text, x, y, width, size, color, bold=False, spacing=12):
    f=font(size,bold); words=text.split(); line=''
    for word in words:
        trial=(line+' '+word).strip()
        if draw.textlength(trial,font=f)>width and line:
            draw.text((x,y),line,font=f,fill=color); y+=size+spacing; line=word
        else: line=trial
    if line: draw.text((x,y),line,font=f,fill=color); y+=size+spacing
    return y

def base():
    img=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(img)
    d.rounded_rectangle((65,40,125,100),18,fill=CORAL)
    d.text((83,46),'D',font=font(35,True),fill=TEXT)
    d.text((143,46),'DhaShu',font=font(35,True),fill=TEXT)
    d.text((65,842),'HOW IT WORKS  /  INVITED BETA WALKTHROUGH',font=font(18),fill=MUTED)
    return img

def slide(scene):
    file,title,eyebrow,body,badge=scene
    img=base(); d=ImageDraw.Draw(img)
    d.text((70,165),eyebrow,font=font(22,True),fill=MINT)
    y=wrap(d,title,65,220,940,57,TEXT,True,10)
    wrap(d,body,70,max(390,y+32),890,32,MUTED,False,17)
    d.rounded_rectangle((65,660,1010,752),20,fill=CARD,outline=LILAC,width=2)
    d.text((90,685),badge,font=font(29,True),fill=LILAC)
    shot=Image.open(INPUT/(file+'.png')).convert('RGB')
    shot.thumbnail((350,758),Image.Resampling.LANCZOS)
    x=1170+(350-shot.width)//2; y=55
    img.paste(shot,(x,y))
    d.rounded_rectangle((x-7,y-7,x+shot.width+7,y+shot.height+7),20,outline=MINT,width=3)
    d.text((1150,835),'App preview · example data',font=font(18),fill=MUTED)
    return img

def table(active=-1):
    img=base();d=ImageDraw.Draw(img)
    d.text((65,127),'Your 30-minute test timetable',font=font(46,True),fill=TEXT)
    d.text((65,194),'3 real minutes per checkpoint · shared server clock · your actions stay manual',font=font(24),fill=MUTED)
    cols=(85,300,740); top=245; rowh=43
    for x,label in zip(cols,('MINUTES','JUMP TO','WHAT HAPPENS')): d.text((x,top),label,font=font(21,True),fill=MINT)
    for i,row in enumerate(ROWS):
        y=top+42+i*rowh
        d.rounded_rectangle((65,y-2,1535,y+rowh-4),8,fill=CARD if i==active else BG)
        for j,(x,value) in enumerate(zip(cols,row)): d.text((x,y+3),value,font=font(23,j==0),fill=MINT if j==0 else TEXT)
        d.line((65,y+rowh-3,1535,y+rowh-3),fill='#3A3154')
    d.text((70,785),'*Latest saved weekend date in this test environment; no plan means these jumps wait at Thu 18:00.',font=font(21),fill=MUTED)
    d.text((70,812),'Stops at next Monday. Test administrator enables the run. No automatic consent or signatures.',font=font(21),fill=MUTED)
    return img

def main():
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    command=[ffmpeg,'-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}',
      '-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',
      '-movflags','+faststart',str(OUTPUT/'how-it-works.mp4')]
    captions=['WEBVTT','']
    def stamp(seconds): return f'00:{seconds//60:02d}:{seconds%60:02d}.000'
    with (INPUT/'encode.log').open('w') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
        for i,scene in enumerate(SCENES):
            frame=slide(scene)
            if i==0: frame.save(OUTPUT/'how-it-works-poster.jpg',quality=90)
            frame.save(INPUT/f'frame-{i:02d}.jpg',quality=85)
            captions += [f'{stamp(i*5)} --> {stamp((i+1)*5)}',scene[1]+'. '+scene[3], '']
            for j in range(5*FPS):
                image=frame.copy();d=ImageDraw.Draw(image)
                # Moving progress and pulsing frame keep the walkthrough animated.
                d.rectangle((0,H-5,int(W*(i*5+j/FPS)/90),H),fill=MINT)
                pulse=int(2+2*(1+math.sin(j/FPS*3)))
                d.rounded_rectangle((1163,48,1527,820),20,outline=LILAC,width=pulse)
                process.stdin.write(image.tobytes())
        for j in range(20*FPS):
            image=table(min(10,int(j/FPS/1.6)));d=ImageDraw.Draw(image)
            d.rectangle((0,H-5,int(W*(70+j/FPS)/90),H),fill=MINT)
            process.stdin.write(image.tobytes())
        process.stdin.close()
        if process.wait()!=0: raise RuntimeError('Video encoding failed; inspect encode.log')
    table(8).save(INPUT/'timetable-preview.jpg',quality=90)
    captions += ['00:01:10.000 --> 00:01:30.000', 'The accelerated test advances every three minutes and stops at next Monday. Review the timetable. Your decisions, consent and signatures are never automated.', '']
    (OUTPUT/'how-it-works.vtt').write_text('\n'.join(captions),encoding='utf-8')
    print(f'Created {OUTPUT / "how-it-works.mp4"} (90 seconds, H.264, no audio).')

if __name__=='__main__': main()
