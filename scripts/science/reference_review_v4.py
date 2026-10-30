"""Recalculo dos 88 gabaritos direto dos Parquets, sem executor/oraculo anterior."""
from pathlib import Path
from decimal import Decimal,localcontext
import csv,json
import duckdb
from consultas_ambientais.evaluation.common import read,sha,digest,save,lines
from .audit import require

D=lambda x:Decimal(str(x))
TEMPORAL={'diferenca_liquida','reducao_liquida','variacao_percentual','diferenca_pontos_percentuais'}
FORMULAS={'area':'A_t; conversao explicita de ha para unidade solicitada',
 'participacao':'100 * A_t / S_t',
 'diferenca_liquida':'A_final - A_inicial',
 'reducao_liquida':'max(0, A_inicial - A_final)',
 'variacao_percentual':'100 * (A_final - A_inicial) / A_inicial',
 'diferenca_pontos_percentuais':'100 * A_final / S_final - 100 * A_inicial / S_inicial'}


def arithmetic(metric,unit,observations):
    with localcontext() as c:
        c.prec=50
        first,den0=map(D,observations[0]);den=[];reason=None
        if metric=='area':value=first
        elif metric=='participacao':
            den=[den0];value=first/den0*100 if den0 else None
            if value is None:reason='suporte_observado_zero'
        else:
            last,den1=map(D,observations[1]);delta=last-first
            if metric=='diferenca_liquida':value=delta
            elif metric=='reducao_liquida':value=-delta if delta<0 else D(0)
            elif metric=='variacao_percentual':
                den=[first];value=delta/first*100 if first else None
                if value is None:reason='base_inicial_zero'
            elif metric=='diferenca_pontos_percentuais':
                den=[den0,den1];value=(last/den1-first/den0)*100 if den0 and den1 else None
                if value is None:reason='suporte_observado_zero'
            else:raise ValueError('metrica_desconhecida')
        if value is not None and unit in {'ha','km2','m2'}:value*=dict(ha=D(1),km2=D('0.01'),m2=D(10000))[unit]
        return {'value':str(value) if value is not None else None,'denominators_ha':[str(v) for v in den],'undefined_reason':reason}


def close(a,b,unit,policy):
    if a is None or b is None:return a is b
    return abs(D(a)-D(b)) <= D(policy['absolute_tolerance'][unit])+D(policy['relative_tolerance'])*abs(D(b))


def build(root,output,human):
    root,output=map(Path,(root,output));old=root/'benchmarks/pt_rn_v1'
    cases=[c for c in lines(old/'cases.jsonl') if c['split']=='test' and c['expected_decision']=='respondida']
    require(len(cases)==88,'universo_quantitativo_divergente');gold=read(old/'gold.json');policy=read(old/'protocol.json');leaves=read(old/'classes.json')
    require(human['case_hashes']=={c['case_id']:digest(c) for c in cases},'declaracao_em_outros_casos')
    run=read(root/'configs/local.json')['run_id'];manifest_path=root/'artifacts/processing'/run/'manifest.json';manifest=read(manifest_path)
    parts={p['territory_code']:p for p in manifest['partitions']};territories={t['code']:t for t in read(root/'data/territories_v1.json')['entries']}
    hashes={str(manifest_path.relative_to(root)):sha(manifest_path)};cache={};invariants=[]
    def load(code):
        if code in cache:return cache[code]
        tables={}
        with duckdb.connect(':memory:') as db:
            db.execute('SET threads=1')
            for f in parts[code]['files']:
                path=root/'data/processed'/run/code/f['name'];require(sha(path)==f['sha256'],'insumo_gabarito_alterado');hashes[str(path.relative_to(root))]=sha(path)
                cursor=db.execute('SELECT * FROM read_parquet(?)',[str(path)]);names=[c[0] for c in cursor.description]
                tables[f['name']]=[dict(zip(names,r)) for r in cursor.fetchall()]
        require(len({(r['support'],r['year'],r['class_code']) for r in tables['areas.parquet']})==len(tables['areas.parquet']),'duplicatas')
        for q in tables['quality.parquet']:
            total=sum((D(r['area_m2']) for r in tables['areas.parquet'] if (r['support'],r['year'])==(q['support'],q['year'])),D(0))
            err=abs(total-D(q['observed_area_m2']));tol=D('.01')+D('1e-9')*D(q['total_area_m2'])
            invariants.append({'territory_code':code,'support':q['support'],'year':q['year'],'error_m2':str(err),'tolerance_m2':str(tol),'passed':err<=tol})
        cache[code]=tables;return tables
    dossiers=[];values_rows=[]
    for case in sorted(cases,key=lambda c:c['case_id']):
        cid=case['case_id'];g=gold[cid];p=g['plan'];support='comum' if p['metric'] in TEMPORAL else 'anual'
        expanded=sorted(set().union(*(set(leaves[str(c)]) for c in p['class_codes'])));calculated=[];operands=[]
        require(p['operation']!='ranking_delimitado','ranking_real_positivo_fora_deste_conjunto')
        for code in sorted(p['territory_codes']):
            t=territories[code];require(not p['scope_uf'] or t['uf']==p['scope_uf'],'UF_incoerente')
            tables=load(code);obs=[]
            for year in p['years']:
                q=[r for r in tables['quality.parquet'] if (r['support'],r['year'])==(support,year)]
                require(len(q)==1 and q[0]['eligible_complete'],'qualidade_insuficiente')
                rs=[r for r in tables['areas.parquet'] if (r['support'],r['year'])==(support,year) and r['class_code'] in expanded]
                require(len(rs)==len(expanded),'classe_ausente')
                area=sum((D(r['area_m2'])/D(10000) for r in rs),D(0));den=D(q[0]['observed_area_m2'])/D(10000)
                obs.append((area,den));operands.append({'territory_code':code,'territory_name':t['name_original'],'uf':t['uf'],
                    'year':year,'support':support,'area_class_ha':str(area),'support_area_ha':str(den),
                    'leaf_areas_ha':{str(r['class_code']):str(D(r['area_m2'])/D(10000)) for r in rs},'common_support_id':q[0]['common_support_id']})
            groups=[(p['years'],obs)] if support=='comum' else [([year],[o]) for year,o in zip(p['years'],obs)]
            for years,oper in groups:calculated.append({'territory_code':code,'years':years,'unit':p['unit'],'rank':None,**arithmetic(p['metric'],p['unit'],oper)})
        key=lambda x:(x['territory_code'],x['years']);expected=sorted(g['values'],key=key);calculated.sort(key=key)
        passed=len(calculated)==len(expected)
        for actual,ref in zip(calculated,expected):
            identity=all(actual[k]==ref[k] for k in ['territory_code','years','unit','rank','undefined_reason'])
            den=actual['denominators_ha'];dr=ref['denominators_ha']
            ok=identity and close(actual['value'],ref['value'],actual['unit'],policy) and len(den)==len(dr) and all(close(a,b,'ha',policy) for a,b in zip(den,dr))
            passed &= ok
            values_rows.append({'case_id':cid,'territory_code':actual['territory_code'],'years':','.join(map(str,actual['years'])),
                'metric':p['metric'],'unit':p['unit'],'reference_value':ref['value'],'recomputed_value':actual['value'],
                'absolute_difference':str(abs(D(actual['value'])-D(ref['value']))) if actual['value'] is not None and ref['value'] is not None else None,
                'denominators_ha':json.dumps(den),'passed':ok})
        dossiers.append({'case_id':cid,'family_id':case['family_id'],'question':case['question'],'canonical_plan':p,'expanded_leaf_codes':expanded,
            'formula':FORMULAS[p['metric']],'operands':operands,'reference':expected,'recomputed':calculated,'automatic_check_passed':passed,
            'human_review':'aprovado_conforme_declaracao_global_do_autor','individual_human_annotations':None,
            'source_run_id':run,'case_sha256':digest(case)})
    require(all(i['passed'] for i in invariants),'invariante_falhou')
    output.mkdir(parents=True,exist_ok=True);save(output/'fichas_88.json',dossiers)
    with (output/'conferencia_valores.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(values_rows[0]));writer.writeheader();writer.writerows(values_rows)
    md=['# Fichas dos 88 gabaritos quantitativos','',
        'Revisao humana declarada globalmente pelo autor, sem correcoes. As fichas foram geradas depois dessa declaracao; nao sao anotacoes humanas preexistentes. Recalculo automatico independente, sem alterar o gabarito congelado.','']
    for d in dossiers:
        md += ['## '+d['case_id'],d['question'],'','Plano: `'+json.dumps(d['canonical_plan'],ensure_ascii=False)+'`','',
            'Folhas unidas sem duplicatas: '+','.join(map(str,d['expanded_leaf_codes'])), 'Formula: '+d['formula'],'',
            '| Territorio | Ano | Suporte | Area da classe (ha) | Suporte observado (ha) |','|---|---|---|---|---|']
        md += ['| '+ ' | '.join(map(str,[r['territory_code'],r['year'],r['support'],r['area_class_ha'],r['support_area_ha']]))+' |' for r in d['operands']]
        md += ['','Referencia: `'+json.dumps(d['reference'],ensure_ascii=False)+'`','Recalculado: `'+json.dumps(d['recomputed'],ensure_ascii=False)+'`','Conferencia automatica: '+str(d['automatic_check_passed']),
            'Declaracao humana: aprovado sem correcoes; anotacoes individuais nao fornecidas.','']
    (output/'FICHAS_88_GABARITOS.md').write_text('\n'.join(md))
    summary={'kind':'recalculo_automatico_independente_sobre_derivados','cases':len(dossiers),'value_rows':len(values_rows),
        'all_passed':all(d['automatic_check_passed'] for d in dossiers),'numeric_tolerance':'mesma do protocolo original congelado; nao incerteza do mapa',
        'input_hashes':hashes,'conservation_invariants':invariants,'human_declaration_sha256':digest(human),
        'limitations':['Compartilha os Parquets de referencia; nao valida verdade de campo nem geracao geoespacial.',
                       'Declaracao humana global, sem fichas originais, cegamento ou revisor independente.',
                       'Recalculo valida o plano canonico; entendimento da pergunta foi revisado conforme declaracao do autor.']}
    save(output/'resumo.json',summary);return summary
