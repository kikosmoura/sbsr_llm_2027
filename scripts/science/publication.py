"""Inventario e varredura tecnica; nao concede licencas nem publica arquivos."""
from pathlib import Path
from zipfile import ZipFile
import json,re,subprocess,ipaddress
from consultas_ambientais.evaluation.common import sha,save


def scan_text(text,secrets=()):
    hits=[]
    if any(s and len(s)>=3 and s in text for s in secrets):hits.append('valor_privado_configurado')
    personal=r'(?:/' + r'home/[^\s"<>]+|/' + r'Users/[^\s"<>]+|[A-Za-z]:\\Users\\[^\s"<>]+)'
    if re.search(personal,text):hits.append('caminho_pessoal')
    if re.search(r'file:///[A-Za-z0-9_/%~.\-]+',text):hits.append('referencia_local_absoluta')
    if re.search(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',text):hits.append('jwt')
    if re.search(r"https?://[^\s\"'<>]*(?:X-Amz-Signature|access_token|signature)=",text,re.I):hits.append('url_assinada')
    for match in re.finditer(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',text):
        try:
            ip=ipaddress.ip_address(match.group())
            if ip.is_private and not ip.is_loopback:hits.append('ip_privado')
        except ValueError:pass
    return sorted(set(hits))


def file_text(path):
    p=Path(path)
    if p.suffix=='.odt':
        with ZipFile(p) as z:return '\n'.join(z.read(n).decode(errors='replace') for n in z.namelist() if n.endswith('.xml'))
    if p.suffix=='.pdf':
        result=subprocess.run(['pdftotext',str(p),'-'],capture_output=True,timeout=30,check=True)
        meta=subprocess.run(['pdfinfo',str(p)],capture_output=True,timeout=30,check=True)
        return result.stdout.decode(errors='replace')+'\n'+meta.stdout.decode(errors='replace')
    if p.suffix=='.parquet':
        import duckdb
        with duckdb.connect(':memory:') as db:
            kv=db.execute('SELECT key,value FROM parquet_kv_metadata(?)',[str(p)]).fetchall()
        return repr(kv)
    if p.suffix in ['.png','.jpg']:
        from PIL import Image
        with Image.open(p) as image:return repr(image.info)+' '+repr(dict(image.getexif()))
    if p.suffix=='.tif':
        import rasterio
        with rasterio.open(p) as raster:return repr(raster.tags())+repr(raster.tags(ns='IMAGE_STRUCTURE'))
    return p.read_text(errors='replace')


def inventory(root,output,secrets=()):
    root=Path(root);output=Path(output);pub=output/'publicacao';pub.mkdir(exist_ok=True)
    groups=[
        ('codigo','src/consultas_ambientais','Proprietary - research prototype (metadado atual); licenca aberta nao definida','pendente_titular','Titular do codigo e instituicao a confirmar; preservar dependencias e avisos.'),
        ('scripts','scripts','licenca do projeto a definir','pendente_titular','Inclui consolidacao, plotagem e geracao do manuscrito; preservar versoes verificadas.'),
        ('testes','tests','licenca do projeto a definir','pendente_titular','Fixtures sinteticas/mocks; nao representam observacoes cientificas.'),
        ('configuracao','configs','licenca do projeto a definir','pendente_titular','Somente configuracao publica e .env.example; nenhum .env real.'),
        ('instalacao','pyproject.toml','licenca do projeto a definir','pendente_titular','Inclui setup.cfg, setup.py, dependencias verificadas e .env.example com placeholders.'),
        ('benchmark','benchmarks/pt_rn_v1','licenca do benchmark a definir; catalogo MapBiomas CC BY 4.0','condicional','Perguntas construidas, gabaritos, protocolos e hashes; revisar autoria/licenca e dados territoriais usados.'),
        ('respostas_individuais','artifacts/evaluation/test_v1','direitos de saidas/modelo/instituicao a confirmar','condicional','Preservar fonte original e hashes; nao incluir tokens, raciocinio interno ou corpos remotos.'),
        ('estatisticas_derivadas','data/processed','MapBiomas CC BY 4.0; malha territorial com licenca nao identificada','bloqueado_licenca_malha','Selecionar exclusivamente a execucao auditada; nao misturar execucoes historicas.'),
        ('snapshot','data/mesh_RN_v1.json','origem/edicao/licenca da malha nao comprovadas','bloqueado_licenca_malha','Nao afirmar que codigos IBGE conferem licenca ou comprovam edicao da geometria.'),
        ('recortes','artifacts/staging','MapBiomas CC BY 4.0 com atribuicao; revisao do espelho nao comprovada','condicional','Somente os dois recortes nativos auditados; excluir cache HTTP nacional e reter hashes/proveniencia.')]
    entries=[]
    for gid,relative,license_name,status,note in groups:
        base=root/relative
        files=[p for p in (base.rglob('*') if base.is_dir() else [base]) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.lock'}]
        if gid=='instalacao':files=[root/n for n in ['pyproject.toml','setup.cfg','setup.py','requirements-verified.txt','.env.example'] if (root/n).is_file()]
        if gid=='estatisticas_derivadas':files=[p for p in files if read_run_id(output) in str(p)]
        if gid=='recortes':
            audit=json.loads((output/'auditoria.json').read_text());allowed=set(audit['crop_hashes']);files=[p for p in files if p.name in ['native_2015.tif','native_2025.tif'] and sha(p) in allowed]
        findings=[]
        for p in files:
            hits=scan_text(file_text(p),secrets)
            if hits:findings.append({'path':str(p.relative_to(root)),'categories':hits})
        entries.append({'artifact':gid,'path':relative,'files':len(files),'bytes':sum(p.stat().st_size for p in files),
                        'license_or_attribution':license_name,'redistribution_state':status,'note':note,
                        'privacy_scan':'verificado' if not findings else 'revisar_antes_de_selecionar','findings':findings})
    generated=[p for p in output.rglob('*') if p.is_file() and 'publicacao' not in p.parts]
    generated_findings=[]
    for p in generated:
        hits=scan_text(file_text(p),secrets)
        if hits:generated_findings.append({'path':str(p.relative_to(output)),'categories':hits})
    # O conteudo gerado para revisao nao pode conter valores privados ou paths pessoais.
    if generated_findings:raise ValueError('material_gerado_requer_redacao: '+','.join(f['path'] for f in generated_findings))
    report={'schema_version':'inventario-publicacao-v1','publication_performed':False,'deployment_performed':False,
            'technical_privacy_is_not_license_clearance':True,'generated_material_privacy_scan':'verificado',
            'artifacts':entries,'excluded':['.env e cofres','.venv/venv','script_exemplo original','cache HTTP e headers OAuth2','logs e sessoes nao selecionadas','exemplos com credenciais','geometrias sem licenca identificada'],
            'mapbiomas_policy':{'url':'https://brasil.mapbiomas.org/faq/','observed_license':'CC BY 4.0','attribution':'Projeto MapBiomas – Colecao 11 da Serie Anual de Mapas de Cobertura e Uso da Terra do Brasil; acesso em 19/10/2026; consultar fontes exatas e hashes no relatorio. Calculos/recortes derivados; revisao do espelho e malha documentadas separadamente.'},
            'pending':['Titular e licenca do codigo/benchmark','Licenca e edicao da malha','Condicoes institucionais de uso/publicacao das saidas LLM','Autoria, afiliacoes e contatos reais','Revisao final do PDF e politicas vigentes na data de submissao']}
    report['scientific_material']={'path':str(output.relative_to(root)) if output.is_relative_to(root) else 'diretorio de saida selecionado',
        'files':len(generated),'privacy_scan':'verificado','redistribution_state':'revisao_autoral_e_direitos_pendentes',
        'note':'Tabelas/figuras/relatorio/manuscrito sao derivados; revisar autoria, direitos e atribuicoes antes de redistribuir.'}
    save(pub/'inventario.json',report)
    md=['# Artefatos candidatos a publicacao — revisao local','',
        'Nenhum arquivo foi publicado. Verificacao tecnica de privacidade nao concede licenca. Os direitos pendentes impedem considerar o conjunto integral liberado. O artigo e as estatisticas estao disponiveis para revisao autoral local.','',
        '| Artefato | Caminho relativo | Arquivos | Estado de redistribuicao | Varredura tecnica |',
        '|---|---|---:|---|---|']
    for e in entries:md.append(f"| {e['artifact']} | {e['path']} | {e['files']} | {e['redistribution_state']} | {e['privacy_scan']} |")
    md.append(f"| material_cientifico | {report['scientific_material']['path']} | {len(generated)} | revisao_autoral_e_direitos_pendentes | verificado |")
    for e in entries:md+=['',f"## {e['artifact']}",'',e['license_or_attribution']+'. '+e['note']]
    md += ['', '## Atribuicao MapBiomas','',report['mapbiomas_policy']['attribution'],'',
           'A pagina oficial de FAQ declara CC BY 4.0 e orienta a referencia da colecao. Nao se extrapola essa licenca para a malha de origem interna ou para o codigo/benchmark. A disponibilizacao de codigo neste workspace nao equivale a permissao de redistribuicao institucional.',
           '', '## Selecionar antes de uma publicacao futura','',
           'Usar somente a execucao geoespacial e o teste identificados no relatorio. Incluir configuracao publica, dependencia fixada, scripts, hashes, benchmark e respostas individuais auditadas. Estatisticas/recortes devem manter atribuicao, metodo, malha/revisao desconhecidas e diagnosticos de qualidade. Excluir ambiente local, exemplo original, logs/headers/tokens, caches e caminhos pessoais. O modelo ODT original nao e proposto para redistribuicao: usar URL/hash oficial; sua licenca explicita nao foi localizada.',
           '', 'Nao foram atribuidos autores presumidos nem aplicada uma licenca nova. As condicoes de redistribuicao do codigo, da malha e das saidas institucionais devem ser resolvidas pelos titulares antes de publicar.','']
    (pub/'INVENTARIO.md').write_text('\n'.join(md))
    return report


def read_run_id(output):return json.loads((Path(output)/'auditoria.json').read_text())['data_run_id']
