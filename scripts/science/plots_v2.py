"""Figuras novas da revisao V2, calculadas dos arquivos individuais consolidados."""
import argparse,json,hashlib
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--metrics',type=Path,required=True);p.add_argument('--sensitivity',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    m=json.loads(args.metrics.read_text());s=json.loads(args.sensitivity.read_text());out=args.output;out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'sbsr2027-v2','pdf.fonttype':42})
    outputs=[]
    def save(fig,name):
        fig.tight_layout()
        for ext in ['png','svg','pdf']:
            path=out/(name+'.'+ext);kwargs={'metadata':{'Creator':'Revisao cientifica V2 por script','CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
            fig.savefig(path,dpi=300,bbox_inches='tight',**kwargs);outputs.append(path.name)
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(3.3,3.4));ax.set_xlim(0,10);ax.set_ylim(0,12.6);ax.axis('off')
    boxes=[(.1,10.5,6.1,1.1,'Pergunta em português'),(.1,8.3,6.1,1.3,'LLM: interpretação\nproposta JSON'),
           (.1,6.1,6.1,1.3,'Validação local\ncontrato + semântica + dados'),(.1,3.4,6.1,1.3,'Executor determinístico\nfunções permitidas + unidades'),
           (.1,.7,6.1,1.5,'Resposta do servidor\ntexto + valores + evidências/IDs'),
           (7.05,3.4,2.65,1.6,'Parquet local\náreas e\nqualidade'),(7.05,5.9,2.65,2.2,'Esclarecer /\nsem dados /\nfora escopo /\nerro técnico')]
    for x,y,w,h,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.05',facecolor='#eef4f6',edgecolor='#385465',lw=1))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=6.4 if x<1 else 5.9)
    for start,end in [((3.15,10.45),(3.15,9.68)),((3.15,8.25),(3.15,7.48)),((3.15,6.05),(3.15,4.78)),((3.15,3.35),(3.15,2.28)),((6.3,6.7),(6.95,6.7)),((6.95,4.05),(6.3,4.05))]:
        ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=10,color='#385465'))
    ax.text(5,12.2,'Pré-cálculo de fontes e áreas fora da pergunta',ha='center',fontsize=6.2)
    ax.text(5,.1,'Sem executar SQL ou código produzido pelo modelo',ha='center',fontsize=6.2)
    save(fig,'fig10_fluxo_componentes_v2')
    entries=[('Principal\npredefinido',m['paired_C_minus_B']),
             ('Comum sem\nfalha técnica*',s['paired_analyses'][0]['paired']),
             ('Quantitativo\ncomum*',s['paired_analyses'][1]['paired'])]
    fig,ax=plt.subplots(figsize=(3.3,2.5))
    for y,(label,r) in enumerate(entries):
        if r.get('state')!='verificado':continue
        v=100*r['difference_C_minus_B'];lo,hi=np.array(r['ci95'])*100
        ax.errorbar(v,y,xerr=[[v-lo],[hi-v]],fmt='o',capsize=3,color='#147d92' if y==0 else '#d17819')
        ax.text(v,y+.23,f'{v:.2f} [{lo:.2f}; {hi:.2f}]',ha='center',fontsize=6.5)
    ax.axvline(0,color='0.45',ls='--',lw=.8);ax.set_yticks(range(len(entries)),[x[0] for x in entries],fontsize=6.7)
    ax.set_ylim(-.45,2.65);ax.invert_yaxis();ax.set_xlabel('C−B (pp); IC95% por famílias',fontsize=7)
    ax.tick_params(labelsize=7);fig.text(.5,.005,'* Pós-hoc, condicionado ao sucesso observado',ha='center',fontsize=6)
    save(fig,'fig11_sensibilidade_v2')
    labels={'retorno_textual_ausente':'Retorno textual ausente','rejeicao_contrato_indeterminada':'Rejeição genérica: causa não preservada',
            'rejeicao_semantica':'Rejeição semântica (status técnico)', 'erro_semantico_decisao':'Erro semântico de decisão',
            'erro_numerico_isolavel':'Erro numérico isolável'}
    lookup={(r['condition'],r['diagnosis']):r['count'] for r in s['diagnostic_counts']}
    fig,ax=plt.subplots(figsize=(7,3.2));ys=np.arange(len(labels))
    for offset,k,color in [(-.17,'B','#d17819'),(.17,'C','#147d92')]:
        values=[lookup[k,category] for category in labels];ax.barh(ys+offset,values,height=.32,color=color,label=k)
        for y,v in zip(ys+offset,values):ax.text(v+.4,y,str(v),va='center',fontsize=8)
    ax.set_yticks(ys,list(labels.values()));ax.invert_yaxis();ax.set_xlabel('Casos; sem dupla contagem de diagnóstico e estado técnico')
    ax.legend(loc='lower right')
    # Limite calculado apenas sobre as categorias exibidas, sem cortar a maior barra.
    ax.set_xlim(0,max(lookup[k,cat] for k in 'BC' for cat in labels)+5)
    ax.set_title('Diagnóstico terminal dos erros; acertos excluídos')
    save(fig,'fig12_diagnosticos_v2')
    (out/'proveniencia_figuras_v2.json').write_text(json.dumps({'metrics_sha256':hashlib.sha256(args.metrics.read_bytes()).hexdigest(),
        'sensitivity_sha256':hashlib.sha256(args.sensitivity.read_bytes()).hexdigest(),'matplotlib':matplotlib.__version__,
        'numpy':np.__version__,'files':outputs,'manual_numeric_editing':False},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
