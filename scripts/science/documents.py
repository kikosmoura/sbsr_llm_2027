"""Rascunho ODT derivado do modelo oficial; metadados refeitos sem nomes presumidos."""
import argparse,json,re,copy
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED,ZIP_STORED
from lxml import etree as E
from PIL import Image

NS={'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0','text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0','fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'draw':'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0','svg':'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'xlink':'http://www.w3.org/1999/xlink','table':'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'manifest':'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0','dc':'http://purl.org/dc/elements/1.1/',
    'meta':'urn:oasis:names:tc:opendocument:xmlns:meta:1.0'}
Q=lambda key:'{'+NS[key.split(':')[0]]+'}'+key.split(':')[1]

def node(tag,attrib=None,text=None):
    e=E.Element(Q(tag),{Q(k):str(v) for k,v in (attrib or {}).items()})
    e.text=text;return e


def serialize(e):return E.tostring(e,encoding='UTF-8',xml_declaration=True)


def make(draft,template,figures,output):
    with ZipFile(template) as z:content=E.fromstring(z.read('content.xml'));styles=E.fromstring(z.read('styles.xml'))
    root_body=content.find('office:body',NS);root_body.clear();body=E.SubElement(root_body,Q('office:text'))
    auto=content.find('office:automatic-styles',NS)
    def para_style(name,align='justify',indent='0cm',size=10,bold=False,italic=False,top='0cm',bottom='0.08cm',keep=False):
        s=node('style:style',{'style:name':name,'style:family':'paragraph','style:parent-style-name':'Standard'})
        pp={'fo:text-align':align,'fo:text-indent':indent,'fo:margin-top':top,'fo:margin-bottom':bottom,'fo:line-height':'100%','fo:orphans':'2','fo:widows':'2'}
        if keep:pp['fo:keep-with-next']='always'
        s.append(node('style:paragraph-properties',pp));tp={'style:font-name':'Times New Roman','fo:font-family':'Times New Roman','fo:font-size':str(size)+'pt','fo:language':'pt','fo:country':'BR','fo:font-style':'italic' if italic else 'normal','fo:font-weight':'bold' if bold else 'normal'}
        s.append(node('style:text-properties',tp));auto.append(s)
    para_style('ResearchTitle','center',size=14,bold=True,top='1.011cm',bottom='0.2cm',keep=True)
    para_style('ResearchAuthors','center',size=10,bottom='0.08cm',keep=True)
    para_style('ResearchNotice','center',size=10,bottom='0.15cm',keep=True)
    para_style('ResearchBody',indent='0.635cm');para_style('ResearchFirst')
    para_style('ResearchHeading','center',bold=True,top='0.35cm',bottom='0.35cm',keep=True)
    para_style('ResearchAbstractHeading','left',bold=True,top='0.08cm',bottom='0.08cm',keep=True)
    para_style('ResearchAbstract',italic=True);para_style('ResearchAbstractTitle','left',bold=True,italic=True,bottom='0.08cm',keep=True)
    para_style('ResearchKeywords','left',bottom='0.2cm');para_style('ResearchKeyEn','left',italic=True,bottom='0.2cm')
    para_style('ResearchFigure','center',bottom='0.04cm',keep=True)
    para_style('ResearchCaption','center',size=9,bold=True,bottom='0.15cm')
    para_style('ResearchTable','center',size=10,bottom='0.06cm')
    para_style('ResearchReference','left',size=10,bottom='0.12cm')
    italic=node('style:style',{'style:name':'ResearchEnglish','style:family':'text'});italic.append(node('style:text-properties',{'fo:font-style':'italic'}));auto.append(italic)
    section_style=node('style:style',{'style:name':'ResearchColumns','style:family':'section'})
    props=node('style:section-properties',{'text:dont-balance-text-columns':'false'});cols=node('style:columns',{'fo:column-count':'2','fo:column-gap':'0.61cm'})
    cols.append(node('style:column',{'style:rel-width':'1*','fo:start-indent':'0cm','fo:end-indent':'0.305cm'}));cols.append(node('style:column',{'style:rel-width':'1*','fo:start-indent':'0.305cm','fo:end-indent':'0cm'}));props.append(cols);section_style.append(props);auto.append(section_style)
    fonts=content.find('office:font-face-decls',NS)
    if fonts is not None and not fonts.xpath('./style:font-face[@style:name="Times New Roman"]',namespaces=NS):fonts.append(node('style:font-face',{'style:name':'Times New Roman','svg:font-family':'Times New Roman','style:font-family-generic':'roman','style:font-pitch':'variable'}))
    for master in styles.findall('.//style:master-page',NS):
        for child in list(master):master.remove(child)
    english=re.compile(r'\b(?:Program of Thoughts|benchmark|snapshot|overviews|timeout|seed|workers?|template|usage|gateway|hash(?:es)?|schema|JSON)\b',re.I)
    def paragraph(parent,text,style='ResearchBody'):
        p=node('text:p',{'text:style-name':style});parent.append(p)
        last=0;tail=None
        for hit in english.finditer(text):
            prefix=text[last:hit.start()]
            if tail is None:p.text=(p.text or '')+prefix
            else:tail.tail=(tail.tail or '')+prefix
            child=node('text:span',{'text:style-name':'ResearchEnglish'},hit.group());p.append(child);tail=child;last=hit.end()
        suffix=text[last:]
        if tail is None:p.text=(p.text or '')+suffix
        else:tail.tail=(tail.tail or '')+suffix
        return p
    paragraph(body,draft['title'],'ResearchTitle');paragraph(body,draft['authors'],'ResearchAuthors');paragraph(body,draft['draft_notice'],'ResearchNotice')
    section=node('text:section',{'text:style-name':'ResearchColumns','text:name':'Artigo'});body.append(section)
    paragraph(section,'Resumo','ResearchAbstractHeading');paragraph(section,draft['abstract_pt'],'ResearchFirst');paragraph(section,'Palavras-chave — '+draft['keywords_pt'],'ResearchKeywords')
    paragraph(section,'Abstract','ResearchAbstractTitle');paragraph(section,draft['abstract_en'],'ResearchAbstract');paragraph(section,'Keywords — '+draft['keywords_en'],'ResearchKeyEn')
    images={};first=True;table_index=0
    for block in draft['blocks']:
        kind=block['kind']
        if kind=='heading':paragraph(section,block['text'],'ResearchHeading');first=True
        elif kind=='paragraph':paragraph(section,block['text'],'ResearchFirst' if first else 'ResearchBody');first=False
        elif kind=='reference':paragraph(section,block['text'],'ResearchReference')
        elif kind=='figure':
            path=Path(figures)/block['file'];target='Pictures/'+path.name;images[target]=path.read_bytes()
            width,height=Image.open(path).size;w=8.40;h=w*height/width
            para=paragraph(section,'','ResearchFigure');frame=node('draw:frame',{'draw:name':path.stem,'text:anchor-type':'as-char','svg:width':f'{w}cm','svg:height':f'{h}cm'})
            frame.append(node('draw:image',{'xlink:href':target,'xlink:type':'simple','xlink:show':'embed','xlink:actuate':'onLoad'}));para.append(frame)
            paragraph(section,block['caption'],'ResearchCaption')
        elif kind=='table':
            table_index+=1;name='ResearchTable'+str(table_index)
            style=node('style:style',{'style:name':name,'style:family':'table'});style.append(node('style:table-properties',{'style:width':'8.40cm','table:align':'center','fo:keep-with-next':'always'}));auto.append(style)
            table=node('table:table',{'table:name':name,'table:style-name':name});section.append(table)
            for i in range(len(block['headers'])):
                colname=name+'C'+str(i);sty=node('style:style',{'style:name':colname,'style:family':'table-column'});sty.append(node('style:table-column-properties',{'style:column-width':f'{8.40/len(block["headers"]):.3f}cm'}));auto.append(sty);table.append(node('table:table-column',{'table:style-name':colname}))
            for row in [block['headers'],*block['rows']]:
                tr=node('table:table-row');table.append(tr)
                for val in row:
                    cell=node('table:table-cell',{'office:value-type':'string'});tr.append(cell);paragraph(cell,str(val),'ResearchTable')
            paragraph(section,block['caption'],'ResearchCaption')
    meta=node('office:document-meta',{'office:version':'1.2'});meta_body=node('office:meta');meta.append(meta_body)
    meta_body.append(node('dc:title',text=draft['title']));meta_body.append(node('dc:language',text='pt-BR'));meta_body.append(node('meta:generator',text='Consolidacao cientifica por script'))
    manifest=node('manifest:manifest',{'manifest:version':'1.2'})
    entries={'mimetype':b'application/vnd.oasis.opendocument.text','content.xml':serialize(content),'styles.xml':serialize(styles),'meta.xml':serialize(meta),**images}
    for name,mime in [('/', 'application/vnd.oasis.opendocument.text'),('content.xml','text/xml'),('styles.xml','text/xml'),('meta.xml','text/xml'),*[(n,'image/png') for n in images]]:
        manifest.append(node('manifest:file-entry',{'manifest:full-path':name,'manifest:media-type':mime}))
    entries['META-INF/manifest.xml']=serialize(manifest)
    with ZipFile(output,'w') as z:
        for name,data in entries.items():
            info=ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=ZIP_STORED if name=='mimetype' else ZIP_DEFLATED;z.writestr(info,data)
    # Arquivo de texto revisavel com os mesmos valores do ODT.
    md=['# '+draft['title'],'',draft['draft_notice'],'',draft['authors'],'','## Resumo','',draft['abstract_pt'],'','## Abstract','',draft['abstract_en']]
    for b in draft['blocks']:
        if b['kind']=='heading':md+=['','## '+b['text'],'']
        elif b['kind'] in ['paragraph','reference']:md += [b['text'],'']
        elif b['kind']=='figure':md += ['!['+b['caption']+'](../figuras/'+b['file']+')','']
        elif b['kind']=='table':
            md += ['| '+' | '.join(b['headers'])+' |','| '+' | '.join('---' for _ in b['headers'])+' |',*['| '+' | '.join(map(str,row))+' |' for row in b['rows']],b['caption'],'']
    Path(output).with_suffix('.md').write_text('\n'.join(md)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--draft',type=Path,required=True);p.add_argument('--template',type=Path,required=True);p.add_argument('--figures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    make(json.loads(a.draft.read_text()),a.template,a.figures,a.output)
    print('ODT gerado com corpo novo, imagens locais e metadados sem autoria presumida.')


if __name__=='__main__':main()
