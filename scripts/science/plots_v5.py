"""Dois orcamentos completos; valores e IC vindos dos registros auditados."""
import argparse,json,hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

def main():
    p=argparse.ArgumentParser();p.add_argument('--low',type=Path,required=True);p.add_argument('--high',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    low=json.loads(a.low.read_text());high=json.loads(a.high.read_text());out=a.output;out.mkdir(exist_ok=True,parents=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'sbsr2027-v5','pdf.fonttype':42})
    fig,(top,bottom)=plt.subplots(2,1,figsize=(3.3,3.0),gridspec_kw={'height_ratios':[2,1.2]})
    for i,(label,color) in enumerate([('B_eq','#c7741d'),('C_eq','#167d92')]):
        rows=[next(r for r in m['conditions'] if r['condition']==label) for m in [low,high]]
        xs=[x+(i-.5)*.34 for x in [0,1]];ys=[r['accuracy']*100 for r in rows]
        top.bar(xs,ys,width=.32,label=label,color=color)
        for x,y,r in zip(xs,ys,rows):top.text(x,y+3,f'{r["correct"]}/{r["cases"]}',ha='center',fontsize=8)
    top.set_xticks([0,1]);top.set_xticklabels(['2.048 tokens','4.096 tokens']);top.set_ylim(0,120);top.set_yticks([0,50,100]);top.set_ylabel('Acerto (%)')
    top.legend(loc='upper center',ncol=2,bbox_to_anchor=(.5,1.26),frameon=False,fontsize=8)
    effects=[m['paired_Ceq_minus_Beq'] for m in [low,high]];xmin=min(0,*[e['ci95'][0]*100 for e in effects]);xmax=max(e['ci95'][1]*100 for e in effects)
    for y,e in zip([1,0],effects):
        value=e['difference_C_minus_B']*100;lo,hi=[x*100 for x in e['ci95']]
        bottom.hlines(y,lo,hi,color='#167d92',lw=2);bottom.plot(value,y,'o',color='#167d92');bottom.vlines([lo,hi],y-.07,y+.07,color='#167d92')
        bottom.text((lo+hi)/2,y+.18,f'{value:.2f} [{lo:.2f}; {hi:.2f}]',ha='center',fontsize=8)
    bottom.set_yticks([1,0]);bottom.set_yticklabels(['2.048','4.096']);bottom.set_ylim(-.4,1.65);bottom.set_xlim(xmin-5,xmax+5)
    bottom.axvline(0,color='.5',ls='--',lw=.8);bottom.set_xlabel('C_eq−B_eq (pp); IC95% por famílias',fontsize=8)
    fig.tight_layout(h_pad=1)
    files=[]
    for ext in ['png','svg','pdf']:
        path=out/('fig16_sensibilidade_v5.'+ext);kw={'metadata':{'Creator':'Revisao cientifica V5','CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
        fig.savefig(path,dpi=300,bbox_inches='tight',**kw);files.append(path.name)
    plt.close(fig)
    (out/'proveniencia_figuras_v5.json').write_text(json.dumps({'source_sha256':{'2048':hashlib.sha256(a.low.read_bytes()).hexdigest(),'4096':hashlib.sha256(a.high.read_bytes()).hexdigest()},
        'matplotlib':matplotlib.__version__,'manual_numeric_editing':False,'files':files},indent=2)+'\n')

if __name__=='__main__':main()
