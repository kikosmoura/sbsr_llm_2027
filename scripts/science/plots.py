"""Figuras cientificas a partir do JSON consolidado, em processo de plotagem isolado."""
import argparse,json,hashlib,os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--metrics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=json.loads(a.metrics.read_text());out=a.output;out.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'sbsr2027-science-v1','pdf.fonttype':42})
    palette=['#6b7280','#d17819','#147d92'];conditions=m['conditions'];labels=[x['condition'] for x in conditions]
    source_hash=hashlib.sha256(a.metrics.read_bytes()).hexdigest();outputs=[]
    def save(fig,name):
        fig.tight_layout()
        for ext in ['png','svg','pdf']:
            path=out/(name+'.'+ext)
            kwargs={'metadata':{'Creator':'Consolidacao cientifica reproduzivel','CreationDate':None,'ModDate':None}} if ext=='pdf' else {}
            fig.savefig(path,dpi=300,bbox_inches='tight',**kwargs);outputs.append(path.name)
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.6),gridspec_kw={'width_ratios':[1,1.2]})
    values=[100*x['accuracy'] for x in conditions]
    axes[0].bar(labels,values,color=palette,width=.62);axes[0].set_ylim(0,110);axes[0].set_ylabel('Acerto ponta a ponta (%)')
    for i,(v,r) in enumerate(zip(values,conditions)):axes[0].text(i,v+2,f'{r["correct"]}/{r["cases"]}',ha='center',fontsize=8)
    entries=[('Principal',m['paired_C_minus_B']),('Quantitativo',m['paired_numeric_subset']),('Por município',m['territory_sensitivity'])]
    for y,(name,r) in enumerate(entries):
        v=r['difference_C_minus_B']*100;lo,hi=np.array(r['ci95'])*100
        axes[1].errorbar(v,y,xerr=[[v-lo],[hi-v]],fmt='o',color=palette[2],capsize=4)
        axes[1].text(v,y+.18,f'{v:.2f} [{lo:.2f}; {hi:.2f}]',ha='center',fontsize=7)
    axes[1].axvline(0,color='0.6',ls='--',lw=.8);axes[1].set_yticks(range(3),[x[0] for x in entries]);axes[1].set_ylim(-.4,2.6);axes[1].invert_yaxis();axes[1].set_xlabel('Diferença pareada C−B (pontos percentuais)')
    axes[1].set_title('IC95% por reamostragem de grupos',fontsize=9);save(fig,'fig01_acerto_ic')
    fids=sorted({x['family_id'] for x in m['families']});lookup={(x['family_id'],x['condition']):x for x in m['families']}
    values=np.array([[lookup[f,k]['accuracy'] for k in labels] for f in fids]);fig,ax=plt.subplots(figsize=(5,6))
    im=ax.imshow(values,vmin=0,vmax=1,cmap='viridis',aspect='auto')
    ax.set_xticks(range(3),labels);ax.set_yticks(range(len(fids)),[f.replace('teste_','') for f in fids]);ax.set_xlabel('Condição');ax.set_title('Acerto por família; contagem correta / casos')
    for y,f in enumerate(fids):
        for x,k in enumerate(labels):
            r=lookup[f,k];ax.text(x,y,f'{r["correct"]}/{r["cases"]}',ha='center',va='center',color='white' if values[y,x]<.55 else 'black',fontsize=8)
    fig.colorbar(im,ax=ax,label='Proporção de acerto');save(fig,'fig02_familias')
    types=sorted({x['type'] for x in m['errors']});error_lookup={(r['condition'],r['type']):r['count'] for r in m['errors']}
    colors=plt.cm.tab20(np.linspace(0,1,len(types)));fig,ax=plt.subplots(figsize=(7.2,3.2));bottom=np.zeros(3)
    for typ,color in zip(types,colors):
        nums=np.array([error_lookup.get((k,typ),0) for k in labels]);legend=typ.replace('_',' ')
        if any(0<v<4 for v in nums):legend+=' ('+', '.join(f'{k}={int(v)}' for k,v in zip(labels,nums))+')'
        ax.bar(labels,nums,bottom=bottom,label=legend,color=color)
        for i,v in enumerate(nums):
            if v>=4:ax.text(i,bottom[i]+v/2,str(int(v)),ha='center',va='center',fontsize=8)
        bottom+=nums
    ax.set_ylabel('Casos (denominador completo)');ax.legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=7);save(fig,'fig03_erros')
    states=['respondida','precisa_esclarecimento','fora_do_escopo','dados_indisponiveis','erro_tecnico'];cols=['#147d92','#d2ad46','#989da4','#a7bbd8','#b44343'];fig,ax=plt.subplots(figsize=(7.2,2.8));bottom=np.zeros(3)
    for status,color in zip(states,cols):
        ns=np.array([next(r['count']/r['denominator'] for r in m['statuses'] if r['condition']==k and r['status']==status)*100 for k in labels]);ax.bar(labels,ns,bottom=bottom,label=status.replace('_',' '),color=color)
        for i,v in enumerate(ns):
            if v>=4:ax.text(i,bottom[i]+v/2,f'{v:.1f}%',ha='center',va='center',fontsize=7)
        bottom+=ns
    ax.set_ylabel('Distribuição dos estados (%)');ax.legend(loc='upper left',bbox_to_anchor=(1,1),fontsize=7);save(fig,'fig04_cobertura_abstencao')
    fig,ax=plt.subplots(figsize=(5,3));data=[[r['latency_seconds'] for r in m['latencies'] if r['condition']==k] for k in labels]
    ax.boxplot(data,labels=labels,showmeans=True);ax.set_ylabel('Latência por caso/condição (s)');ax.set_xlabel('Três workers locais; inclui falhas');save(fig,'fig05_latencia')
    fig,axes=plt.subplots(1,2,figsize=(6.7,2.8));axes[0].bar(labels,[r['tokens_observed']['total_tokens'] for r in conditions],color=palette)
    axes[0].set_ylabel('Tokens totais observados');axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
    axes[1].bar(labels,[r['usage_missing_attempts'] for r in conditions],color=palette);axes[1].set_ylabel('Tentativas sem usage');fig.suptitle('Contadores parciais do gateway; custo desconhecido',fontsize=9);save(fig,'fig06_tokens')
    fig,ax=plt.subplots(figsize=(7.1,3));ax.set_xlim(0,10);ax.set_ylim(0,5);ax.axis('off')
    boxes=[(.1,2,1.8,1,'Pergunta em\nportuguês'),(2.5,3.6,2.2,.9,'A: documentação'),(2.5,2,2.2,.9,'B: documentação\n+ tabelas'),(2.5,.4,2.2,.9,'C: catálogo\n+ plano tipado'),(5.35,.4,1.7,.9,'Executor\npermitido'),(7.6,.4,2.2,.9,'Resposta e\nevidências'),(7.6,2,2.2,.9,'Números emitidos\npelo modelo'),(7.6,3.6,2.2,.9,'Abstenção sem\nevidência')]
    for x,y,w,h,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.08',facecolor='#eef4f6',edgecolor='#385465'));ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=8)
    for start,end in [((1.9,2.5),(2.45,4.05)),((1.9,2.5),(2.45,2.45)),((1.9,2.5),(2.45,.85)),((4.75,4.05),(7.5,4.05)),((4.75,2.45),(7.5,2.45)),((4.75,.85),(5.25,.85)),((7.1,.85),(7.5,.85))]:
        ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=12,color='#385465'))
    ax.text(5.9,1.65,'Parquet local: mesmas fontes e malha',ha='center',fontsize=8);ax.text(5.95,0,'O LLM não executa SQL ou código livre',ha='center',fontsize=8);save(fig,'fig07_arquitetura')
    # Versoes para uma coluna do artigo: fonte legivel na escala final.
    fig,ax=plt.subplots(figsize=(3.3,2.2))
    for y,(name,r) in enumerate(entries):
        v=r['difference_C_minus_B']*100;lo,hi=np.array(r['ci95'])*100
        ax.errorbar(v,y,xerr=[[v-lo],[hi-v]],fmt='o',color=palette[2],capsize=3)
        ax.text(v,y+.22,f'{v:.2f} [{lo:.2f}; {hi:.2f}]',ha='center',fontsize=7)
    ax.axvline(0,color='0.5',ls='--',lw=.7);ax.set_yticks(range(3),[e[0] for e in entries],fontsize=7)
    ax.set_ylim(-.4,2.6);ax.invert_yaxis();ax.set_xlabel('C−B (pontos percentuais); IC95%',fontsize=7)
    ax.tick_params(labelsize=7);save(fig,'fig08_ic_artigo')
    fig,ax=plt.subplots(figsize=(3.3,2.3));ax.set_xlim(0,10);ax.set_ylim(0,5);ax.axis('off')
    boxes=[(.05,3.6,2.7,.9,'A: documentação'),(3.25,3.6,2.3,.9,'Modelo'),(6.2,3.6,3.5,.9,'Sem evidências\nnuméricas'),
           (.05,2,2.7,.9,'B: documentação\n+ tabelas'),(3.25,2,2.3,.9,'Modelo'),(6.2,2,3.5,.9,'Números do\nmodelo'),
           (.05,.4,2.7,.9,'C: catálogo\n+ pergunta'),(3.25,.4,2.3,.9,'Plano validado\n+ executor'),(6.2,.4,3.5,.9,'Resposta e\nevidências')]
    for x,y,w,h,text in boxes:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.04',facecolor='#eef4f6',edgecolor='#385465'))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=6.3)
    for y in [4.05,2.45,.85]:
        for x0,x1 in [(2.78,3.2),(5.58,6.15)]:ax.add_patch(FancyArrowPatch((x0,y),(x1,y),arrowstyle='-|>',mutation_scale=9,color='#385465'))
    ax.text(5,4.8,'Mesma pergunta e identificador de modelo',ha='center',fontsize=7)
    ax.text(5,0,'B e C: mesmas estatísticas locais',ha='center',fontsize=7);save(fig,'fig09_arquitetura_artigo')
    (out/'proveniencia_figuras.json').write_text(json.dumps({'source_metrics_sha256':source_hash,'matplotlib':matplotlib.__version__,'numpy':np.__version__,'files':outputs,'manual_numeric_editing':False},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
