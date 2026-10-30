"""Figura em uma coluna, gerada somente das estatisticas auditadas."""
import argparse,json,hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

def main():
    p=argparse.ArgumentParser();p.add_argument('--metrics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=json.loads(a.metrics.read_text());rows=m['conditions'];e=m['paired_Ceq_minus_Beq'];out=a.output;out.mkdir(exist_ok=True,parents=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'sbsr2027-v4','pdf.fonttype':42})
    fig,(top,bottom)=plt.subplots(2,1,figsize=(3.3,2.8),gridspec_kw={'height_ratios':[2,1]})
    v=[100*r['accuracy'] for r in rows];top.bar([r['condition'] for r in rows],v,color=['#c7741d','#167d92'],width=.55)
    top.set_ylim(0,118);top.set_yticks([0,50,100]);top.set_ylabel('Acerto (%)');top.set_title('Mesmo plano + mesmo JSON final',fontsize=8)
    for i,r in enumerate(rows):top.text(i,v[i]+3,f'{r["correct"]}/{r["cases"]}',ha='center',fontsize=8)
    lo,hi=[x*100 for x in e['ci95']];value=e['difference_C_minus_B']*100
    bottom.hlines(0,lo,hi,color='#167d92',lw=2);bottom.plot(value,0,'o',color='#167d92');bottom.vlines([lo,hi],-.06,.06,color='#167d92')
    bottom.axvline(0,color='.5',ls='--',lw=.8);bottom.set_yticks([]);bottom.set_ylim(-.3,.4)
    bottom.set_xlim(min(0,lo)-5,max(hi,value)+5)
    bottom.text(value,.14,f'{value:.2f} [{lo:.2f}; {hi:.2f}] pp',ha='center',fontsize=8)
    bottom.set_xlabel('C_eq−B_eq; IC95% por famílias',fontsize=8)
    fig.tight_layout(h_pad=.7)
    files=[]
    for ext in ['png','svg','pdf']:
        path=out/('fig15_controle_v4.'+ext);kw={'metadata':{'Creator':'Revisao cientifica V4','CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
        fig.savefig(path,dpi=300,bbox_inches='tight',**kw);files.append(path.name)
    plt.close(fig)
    (out/'proveniencia_figuras_v4.json').write_text(json.dumps({'source_sha256':hashlib.sha256(a.metrics.read_bytes()).hexdigest(),
        'matplotlib':matplotlib.__version__,'files':files,'manual_numeric_editing':False},indent=2)+'\n')

if __name__=='__main__':main()
