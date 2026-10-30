"""A/B: resposta final calculada pelo modelo; nenhum executor chamado aqui."""
import hashlib
import json
import time
from pathlib import Path
from pydantic import ValidationError
from .common import canonical, digest
from .models import BaselineAnswer
from ..llm.interpreting import strict_json
from ..llm.grounding import policy, PolicyStop
from ..llm.client import GatewayError


def run_baseline(condition, question, bundle, client, redactor, max_context_bytes=131072):
    start=time.monotonic();attempts=[]
    try:policy(question)
    except PolicyStop as e:
        return {'status':e.status,'plan':None,'values':[],'clarification_field':None,'reason':e.reason}, attempts, time.monotonic()-start, None
    prompt_dir=Path(__file__).parent/'prompts'
    context={'documentation':(prompt_dir/'documentation.txt').read_text(),'catalog_and_scope':bundle['context']}
    if condition=='B':
        context['tables']=bundle['tables'];context['table_columns']=bundle['table_columns']
    if bundle.get('truncated') or len(canonical(context).encode())>max_context_bytes:
        return failure('contexto_excede_limite_sem_truncamento'),attempts,time.monotonic()-start,None
    system=(prompt_dir/'baseline.txt').read_text()
    user=canonical({'condition':condition,'question':question,'context':context,'output_contract':BaselineAnswer.model_json_schema()})
    messages=[{'role':'system','content':system},{'role':'user','content':user}]
    initial_hash=digest(messages)
    for n in range(2):
        attempt={'number':n+1,'kind':'inicial' if n==0 else 'reparo','messages_sha256':digest(messages), 'issues':[], 'usage':None}
        try:
            response=client.chat(messages)
            attempt.update(latency_seconds=response.elapsed_seconds,usage=response.usage,returned_model=redactor.model_name(response.model),chat_requests=response.chat_requests,
                           output_sha256=hashlib.sha256(response.text.encode()).hexdigest(),output_chars=len(response.text))
            safe,redactions=redactor.clean(response.text)
            if redactions:raise ValueError('saida_redigida')
            parsed=BaselineAnswer.model_validate(strict_json(safe))
            attempt['state']='valida';attempts.append(attempt)
            return parsed.model_dump(mode='json'),attempts,time.monotonic()-start,initial_hash
        except GatewayError as e:
            attempt.update(state='falha_gateway',gateway_error=e.code,http_status=e.status);attempts.append(attempt)
            return failure('falha_gateway'),attempts,time.monotonic()-start,initial_hash
        except (ValueError,TypeError,ValidationError) as e:
            issues=[{'path':list(x['loc']),'code':x['type']} for x in e.errors(include_input=False,include_url=False)] if isinstance(e,ValidationError) else [{'path':[],'code':'json_invalido'}]
            attempt.update(state='invalida',issues=issues);attempts.append(attempt)
            # Nao reenviar texto bruto, gold, numeros esperados ou saida potencialmente sensivel.
            messages=[{'role':'system','content':system},{'role':'user','content':user},
                      {'role':'user','content':canonical({'repair':'A resposta anterior violou o contrato. Produza novamente somente JSON.', 'validation_issues':issues})}]
    return failure('saida_invalida_apos_reparo'),attempts,time.monotonic()-start,initial_hash


def failure(reason):
    return {'status':'erro_tecnico','plan':None,'values':[],'clarification_field':None,'reason':reason}
