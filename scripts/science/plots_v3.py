"""Controle com contrato equivalente: fluxo e resultados a partir de JSON auditado."""
import argparse,json,hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch


def main():
    p=argparse.ArgumentParser();p.add_argument('--metrics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=json.loads(a.metrics.read_text());out=a.output;out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'sbsr2027-v3','pdf.fonttype':42})
    files=[]
    def save(fig,name):
        fig.tight_layout()
        for ext in ['png','svg','pdf']:
            path=out/(name+'.'+ext);kw={'metadata':{'Creator':'Revisao cientifica V3','CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
            fig.savefig(path,dpi=300,bbox_inches='tight',**kw);files.append(path.name)
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(3.3,2.7));ax.set_xlim(0,10);ax.set_ylim(0,10);ax.axis('off')
    boxes=[(.25,8,9.5,1.2,'Mesmo plano de referência + tabelas'),
           (.15,4.4,4.3,1.8,'B_eq: LLM\ncalcula e finaliza'),(5.4,4.4,4.45,1.8,'C_eq: executor\n→ mesmo LLM'),
           (.25,.6,9.5,1.6,'Mesmo contrato JSON e validador\nestado, valores, unidade e denominador')]
    for x,y,w,h,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.04',facecolor='#eef4f6',edgecolor='#385465'))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=6.5)
    for start,end in [((2.2,7.9),(2.2,6.3)),((7.6,7.9),(7.6,6.3)),((2.2,4.3),(2.2,2.3)),((7.6,4.3),(7.6,2.3))]:
        ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',color='#385465',mutation_scale=10))
    ax.text(5,7.1,'Apenas C_eq recebe\nresultado do cálculo',ha='center',va='center',fontsize=6.2)
    ax.text(5,3.3,'Mesmo LLM gera\nambas as respostas',ha='center',va='center',fontsize=6.2)
    save(fig,'fig13_controle_contrato_v3')
    rows=data['conditions'];effect=data['paired_Ceq_minus_Beq']
    fig,axes=plt.subplots(1,2,figsize=(6.5,2.6),gridspec_kw={'width_ratios':[1,1.3]})
    values=[100*r['accuracy'] for r in rows];axes[0].bar([r['condition'] for r in rows],values,color=['#d17819','#147d92'])
    axes[0].set_ylim(0,113);axes[0].set_ylabel('Acerto sob plano fixo (%)')
    for i,r in enumerate(rows):axes[0].text(i,values[i]+2,f'{r["correct"]}/{r["cases"]}',ha='center',fontsize=8)
    v=100*effect['difference_C_minus_B'];lo,hi=[100*x for x in effect['ci95']]
    axes[1].hlines(0,lo,hi,color='#147d92',linewidth=2);axes[1].scatter([v],[0],color='#147d92')
    axes[1].vlines([lo,hi],-.06,.06,color='#147d92');axes[1].axvline(0,color='0.6',ls='--',lw=.8)
    axes[1].text(v,.16,f'{v:.2f} [{lo:.2f}; {hi:.2f}]',ha='center',fontsize=8)
    axes[1].set_ylim(-.4,.45);axes[1].set_yticks([]);axes[1].set_xlabel('C_eq−B_eq (pp); IC95% por famílias')
    axes[1].set_title(f'{effect["cases"]} pares; {effect["groups"]} famílias',fontsize=9)
    save(fig,'fig14_resultados_controle_v3')
    (out/'proveniencia_figuras_v3.json').write_text(json.dumps({'source_sha256':hashlib.sha256(a.metrics.read_bytes()).hexdigest(),
        'matplotlib':matplotlib.__version__,'files':files,'manual_numeric_editing':False},indent=2)+'\n')


if __name__=='__main__':main()
