"""
ui_figures.py — regenerate the two VetScribe interface figures used in the paper.

These are faithful matplotlib renderings of the live Gradio interface (used
because a headless browser was unavailable). Edit colours/text here and call
render_capture(path) / render_review(path), or run the figures notebook.
"""
import textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle

BG="#0b0e13"; CARD="#161b22"; TEAL="#2ea37d"; TEAL2="#1D9E75"; TXT="#e6e8eb"; MUT="#9aa4ad"
INDIGO="#4f46e5"; LBL="#312e81"; AMBER="#BA7517"; AMBTX="#f0d8a8"

def _card(ax,x,y,w,h,fc=CARD,ec="#2a3138",lw=1,r=0.02):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle=f"round,pad=0,rounding_size={r}",fc=fc,ec=ec,lw=lw))

def render_capture(path="ui_capture_view.png"):
    fig,ax=plt.subplots(figsize=(9,7.2)); ax.set_xlim(0,100); ax.set_ylim(0,100); ax.axis("off")
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    t=lambda x,y,s,**k: ax.text(x,y,s,**k)
    t(3,96,"VetScribe",color=TEAL,fontsize=18,fontweight="bold",va="center")
    ax.add_patch(FancyBboxPatch((24,94.7),13,2.5,boxstyle="round,pad=0,rounding_size=1.2",fc=TEAL2,ec="none"))
    t(30.5,95.95,"RESEARCH PROTOTYPE",color="white",fontsize=7,fontweight="bold",ha="center",va="center")
    t(97,96,"08:12",color=TEAL,fontsize=11,fontweight="bold",ha="right",va="center")
    ax.add_patch(FancyBboxPatch((3,89),94,3.4,boxstyle="round,pad=0,rounding_size=0.4",fc="#241d10",ec="none"))
    ax.add_patch(plt.Rectangle((3,89),0.5,3.4,color=AMBER))
    t(5,90.7,"Research prototype — do not upload real, identifiable recordings to the public demo. Synthetic or pre-consented audio only.",color=AMBTX,fontsize=8,va="center")
    t(3,85.5,"1 . PATIENT & MODEL",color=TEAL,fontsize=8.5,fontweight="bold")
    def lblbox(x,w,lab,val):
        pw=min((len(lab)*0.62+3),w)
        ax.add_patch(FancyBboxPatch((x,81.2),pw,2.4,boxstyle="round,pad=0,rounding_size=0.5",fc=LBL,ec="none"))
        t(x+0.8,82.4,lab,color="#cfd3da",fontsize=7.3,fontweight="bold",va="center")
        _card(ax,x,76.6,w,4,r=0.5); t(x+1.2,78.6,val,color=TXT,fontsize=10.5,va="center")
    lblbox(3,28,"Patient","Max"); lblbox(33,40,"Species / breed","Canine — Golden Retriever"); lblbox(76,21,"Age","4y MN")
    ax.add_patch(FancyBboxPatch((3,71.5),24,2.4,boxstyle="round,pad=0,rounding_size=0.5",fc=LBL,ec="none"))
    t(3.8,72.7,"Model (SOAP & flags)",color="#cfd3da",fontsize=7.3,fontweight="bold",va="center")
    _card(ax,3,66.9,42,4,r=0.5); t(4.2,68.9,"gpt-5.4",color=TXT,fontsize=10.5,va="center")
    t(49,68.9,"[ ] Compare vs alternate",color="#cfd3da",fontsize=10,va="center")
    t(3,62,"2 . RECORD CONSULTATION",color=TEAL,fontsize=8.5,fontweight="bold")
    _card(ax,3,50,94,10,fc="#11161d",ec="#234034",lw=1.2,r=0.22)
    ax.add_patch(Circle((9,55),2.5,color=TEAL2)); t(9,55,">",color="white",fontsize=13,ha="center",va="center")
    for i,x in enumerate(np.linspace(15,80,78)):
        h=0.6+abs(np.sin(i*0.5)*np.cos(i*0.17))*3.4
        ax.add_patch(plt.Rectangle((x,55-h/2),0.45,h,color="#3ec79a"))
    t(15,51.6,"08:12 . recording ready — play to review before processing",color=MUT,fontsize=8.3)
    for yy,lab in [(56,"Record again"),(52,"Delete")]:
        ax.add_patch(FancyBboxPatch((83.5,yy),13,2.5,boxstyle="round,pad=0,rounding_size=1.2",fc="none",ec="#46505a",lw=1))
        t(90,yy+1.25,lab,color="#cfd3da",fontsize=7.6,ha="center",va="center")
    ax.add_patch(FancyBboxPatch((3,43),94,5,boxstyle="round,pad=0,rounding_size=0.4",fc=INDIGO,ec="none"))
    t(50,45.5,"Process consultation",color="white",fontsize=13,fontweight="bold",ha="center",va="center")
    steps=["Record","Transcribe","Diarize","Generate","Export"]; cx=[12,32,52,72,92]
    ax.plot([12,72],[36,36],color=TEAL2,lw=2,zorder=0)
    for i,(x,s) in enumerate(zip(cx,steps)):
        if i<4: ax.add_patch(Circle((x,36),1.9,color=TEAL2,zorder=2)); t(x,36,"v",color="white",fontsize=10,ha="center",va="center",zorder=3)
        else: ax.add_patch(Circle((x,36),1.9,fc=BG,ec=TEAL,lw=2,zorder=2)); t(x,36,"5",color=TEAL,fontsize=9,ha="center",va="center",fontweight="bold",zorder=3)
        t(x,32,s,color=TEAL,fontsize=8.3,ha="center")
    plt.savefig(path,dpi=150,bbox_inches="tight",facecolor=BG); plt.close()
    return path

def render_review(path="ui_review_view.png"):
    fig,ax=plt.subplots(figsize=(9,8.2)); ax.set_xlim(0,100); ax.set_ylim(0,100); ax.axis("off")
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    t=lambda x,y,s,**k: ax.text(x,y,s,**k)
    t(3,97,"3 . REVIEW",color=TEAL,fontsize=8.5,fontweight="bold")
    tabs=["Transcript","SOAP note","Owner summary","Insights"]; tx=[6,24,46,72]; on=1
    ax.plot([3,97],[92.5,92.5],color="#2a3138",lw=1)
    for i,(x,tt) in enumerate(zip(tx,tabs)):
        t(x,94,tt,color=TEAL if i==on else MUT,fontsize=10.5,fontweight="bold" if i==on else "normal")
        if i==on: ax.plot([x-1,x+13],[92.3,92.3],color=TEAL2,lw=2.4)
    def soap(y,lab,body):
        t(3,y,lab.upper(),color=TEAL,fontsize=8,fontweight="bold")
        wrapped=textwrap.fill(body,width=108)
        t(3,y-1.6,wrapped,color="#dfe3e8",fontsize=8.8,va="top",linespacing=1.45)
        return wrapped.count("\n")+1
    y=89
    for lab,body in [("Subjective","Owner reports 3 days of lethargy and decreased appetite since the weekend, with increased water intake (polydipsia). Hiking in a wooded area twice the previous weekend."),
    ("Objective","T 102.8 F (mildly elevated). Mild submandibular lymphadenopathy on palpation."),
    ("Assessment","Suspected tick-borne illness; differentials include Lyme disease, Ehrlichiosis and Anaplasmosis given exposure. Polydipsia is atypical and warrants metabolic work-up."),
    ("Plan","CBC and tick-borne disease panel; include renal values and USG. If positive, doxycycline 10 mg/kg PO BID for 28 days. Recheck in 5-7 days.")]:
        n=soap(y,lab,body); y-=(n*2.1+3.4)
    ax.add_patch(FancyBboxPatch((3,y-1.5),94,3.2,boxstyle="round,pad=0,rounding_size=0.4",fc="#241d10",ec="none"))
    ax.add_patch(plt.Rectangle((3,y-1.5),0.5,3.2,color=AMBER))
    t(5,y+0.1,"AI-generated . a clinician must verify before signing.",color=AMBTX,fontsize=8.5,va="center")
    y-=6
    for i,(v,l) in enumerate([("8m 12s","Consult duration"),("~5.4 min*","Est. time saved"),("58%","Vet talk ratio"),("11","Entities")]):
        x=3+i*23.5; _card(ax,x,y-5,22.2,5,fc="#13181f",ec="#252c34",r=0.4)
        t(x+1.5,y-1.6,v,color=TEAL,fontsize=14,fontweight="bold",va="center")
        t(x+1.5,y-3.9,l.upper(),color=MUT,fontsize=6.8,va="center")
    y-=8.5
    t(3,y,"Clinical entities",color="#cfd3da",fontsize=9,fontweight="bold"); y-=2.6
    chips=[("lethargy","f"),("decreased appetite","f"),("polydipsia","f"),("lymphadenopathy","f"),("Lyme disease","d"),("Ehrlichiosis","d"),("Anaplasmosis","d"),("CBC","p"),("tick-borne panel","p"),("doxycycline","dr"),("recheck 5-7d","fu")]
    cols={"f":"#1d3a30","d":"#3a2f15","p":"#22262c","dr":"#2b2752","fu":"#1f5040"}
    x=3
    for txt,ty in chips:
        w=len(txt)*0.62+3.5
        if x+w>97: x=3; y-=3.2
        ax.add_patch(FancyBboxPatch((x,y-2.4),w,2.4,boxstyle="round,pad=0,rounding_size=1.2",fc=cols[ty],ec="#3a4049",lw=0.6))
        t(x+w/2,y-1.2,txt,color="#e6e8eb",fontsize=7.8,ha="center",va="center"); x+=w+1.5
    y-=5
    t(3,y,"Research flags . human-AI gap . 1",color="#b9c0c7",fontsize=8.5,fontweight="bold"); y-=4.2
    ax.add_patch(FancyBboxPatch((3,y-3.2),94,5.6,boxstyle="round,pad=0,rounding_size=0.4",fc="#221c11",ec="none"))
    ax.add_patch(plt.Rectangle((3,y-3.2),0.5,5.6,color=AMBER))
    t(5,y+1.1,"Polydipsia under-weighted as a differential driver",color="#ecdcc0",fontsize=8.8,fontweight="bold",va="center")
    t(5,y-1.4,'Evidence: "drinking way more water than usual" — increased thirst can indicate concurrent\nmetabolic or renal disease and merits its own work-up.',color="#bfb39a",fontsize=7.6,va="center",linespacing=1.4)
    plt.savefig(path,dpi=150,bbox_inches="tight",facecolor=BG); plt.close()
    return path

if __name__ == "__main__":
    print(render_capture()); print(render_review())
