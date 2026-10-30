"""Contrato equivalente: testes sinteticos/mocks, nao resultados cientificos."""
import json,sys
from pathlib import Path
import pytest
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from science.equivalent_v3 import EquivalentAnswer,model_messages,complete
from consultas_ambientais.llm.client import ChatResult,GatewayError
from consultas_ambientais.llm.privacy import Redactor


def valid():
    return {'status':'respondida','values':[{'territory_code':'2400109','years':[2015],
        'value':10,'unit':'ha','denominators_ha':[],'rank':None,'undefined_reason':None}]}


def test_inputs_differ_only_by_executor_observation_and_share_one_schema():
    common={'question':'Pergunta sintetica','validated_plan':{'operation':'area'},'tables':[]}
    schema=EquivalentAnswer.model_json_schema();a=model_messages(common,[],schema,'mesmo sistema')
    b=model_messages(common,[valid()],schema,'mesmo sistema')
    assert a[0]==b[0]
    left=json.loads(a[1]['content']);right=json.loads(b[1]['content'])
    assert left.pop('execution_observations')==[] and right.pop('execution_observations')==[valid()]
    assert left==right and 'reference' not in left and 'condition' not in left


def test_no_plan_output_and_null_requires_explicit_reason():
    bad=valid();bad['plan']={'operation':'area'}
    with pytest.raises(ValidationError):EquivalentAnswer.model_validate(bad)
    bad=valid();bad['values'][0]['value']=None
    with pytest.raises(ValidationError):EquivalentAnswer.model_validate(bad)
    bad['values'][0]['undefined_reason']='base_inicial_zero'
    assert EquivalentAnswer.model_validate(bad).values[0].value is None


def test_maximum_one_repair_without_gold_or_original_raw_output():
    class Client:
        calls=[]
        def chat(self,messages):
            self.calls.append(messages)
            text='invalid_output' if len(self.calls)==1 else json.dumps(valid())
            return ChatResult(text,'mock-model',{'total_tokens':2},.1,1)
    client=Client();messages=[{'role':'user','content':'contexto_sintetico'}]
    result,attempts,_=complete(messages,client,Redactor(),4096)
    assert result['status']=='respondida' and len(attempts)==2
    assert attempts[0]['state']=='invalida' and attempts[1]['state']=='valida'
    assert 'invalid_output' not in str(client.calls[1]) and 'validation_issues' in str(client.calls[1])


def test_gateway_failure_stays_technical_and_no_fake_values():
    class Client:
        def chat(self,messages):raise GatewayError('timeout')
    observed,attempts,_=complete([{'role':'user','content':'sintetico'}],Client(),Redactor(),4096)
    assert observed['status']=='erro_tecnico' and observed['values']==[]
    assert len(attempts)==1 and attempts[0]['gateway_error']=='timeout'


def test_oversized_context_never_calls_model():
    class Client:
        def chat(self,messages):raise AssertionError('nao deve chamar')
    observed,attempts,_=complete([{'role':'user','content':'x'*100}],Client(),Redactor(),10)
    assert observed['reason']=='contexto_excede_limite' and attempts==[]
