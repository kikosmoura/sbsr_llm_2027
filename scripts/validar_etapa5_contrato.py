"""Teste de contrato: HTTP MOCK + Parquets REAIS existentes, sem rede.

As respostas do mock contêm apenas propostas de plano. Não mede a qualidade de
interpretação do LLM; os valores são produzidos pelo executor da etapa 4.
Execute na raiz do projeto, com seu .venv e os dados derivados já presentes.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from consultas_ambientais.llm.client import GatewayClient
from consultas_ambientais.llm.conversation import ConversationService
from consultas_ambientais.llm.prompting import PromptBundle, interpreter_digest
from consultas_ambientais.queries.engine import executor_digest
from consultas_ambientais.settings import LLMSettings, ProjectConfig
from consultas_ambientais.storage.dialogues import private_json

RUN = 'a98ccf54c8c82ceeb601ce126cdb379add4de253912a46267601cdc7d9a29802'


def response(payload):
    value = requests.Response()
    value.status_code = 200
    value._content = json.dumps(payload, ensure_ascii=False).encode()
    value._content_consumed = True
    return value


class MockHTTP:
    """Nunca conecta. Nenhum token/Authorization é gravado no relatório."""
    def __init__(self, proposals):
        self.proposals = iter(proposals)
        self.token_calls = 0
        self.chat_calls = 0

    def post(self, url, **kwargs):
        if url.endswith('/token'):
            self.token_calls += 1
            return response({'access_token': 'mock-access-not-valid', 'expires_in': 300})
        self.chat_calls += 1
        payload = next(self.proposals)
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return response({'choices': [{'message': {'content': text}}], 'model': 'mock-contract-model'})

    def close(self):
        pass


def proposal(city='Riachuelo', uf='RN', cls='pastagem', years=None, **changes):
    intent = dict(operation='area', territories=[dict(mention=city, **({'uf_mention': uf} if uf else {}))],
                  classes=[{'mention': cls}], years=years or [2015], metric='area',
                  metric_mention='área', unit_mention='hectares')
    intent.update(changes)
    return {'action': 'consultar', 'intent': intent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default=RUN)
    parser.add_argument('--output', type=Path, default=Path('reports/etapa5/contrato_dados_reais.json'))
    args = parser.parse_args()
    root = Path.cwd()
    project = ProjectConfig.load(root / 'configs/project.json')
    references = json.loads((root / 'docs/VALIDACAO_ETAPA4.json').read_text())
    reference_ids = {c['case']: c['answer_id'] for c in references['real_cases']}
    cfg = LLMSettings(base_url='https://gateway.example.test/v1', token_url='https://auth.example.test/token',
                      client_id='mock-contract-client', client_secret='mock-secret-not-valid',
                      model='mock-contract-model', max_tokens=768)
    records = []

    def execute(name, question, proposals, expected, reference=None, reply=None):
        http = MockHTTP(proposals)
        client = GatewayClient(cfg, session=http)
        try:
            service = ConversationService(root, project, args.run_id, root / 'data/territories_v1.json',
                                          root / 'data/capabilities_stage3.json', client, cfg,
                                          integration_kind='mock_contrato')
            answer = service.ask(question)
            checks = [answer.status.value == expected]
            turns = [answer]
            if reply:
                assert answer.clarification is not None
                answer = service.ask(reply, answer.session_id, answer.clarification.clarification_id)
                checks.append(answer.status.value == 'respondida')
                turns.append(answer)
            if reference:
                checks.append(answer.query is not None and answer.query.answer_id == reference_ids[reference])
            for a in turns:
                assert a.integration_kind == 'mock_contrato'
                assert all(attempt.usage is None for attempt in a.attempts)
                if a.query and a.query.values:
                    checks.append(all(v.evidence_id in {e.evidence_id for e in a.query.evidence} for v in a.query.values))
            record = {'case': name, 'checks_passed': all(checks), 'mock_http_chat_calls': http.chat_calls,
                      'mock_http_token_calls': http.token_calls, 'real_gateway_called': False,
                      'turns': [{'session_id': a.session_id, 'turn_id': a.turn_id, 'status': a.status.value,
                                 'reason': a.reason, 'audit_path': f'artifacts/dialogues/{a.session_id}/{a.turn_id}.json',
                                 'answer_id': a.query.answer_id if a.query else None,
                                 'values': [v.model_dump(mode='json') for v in a.query.values] if a.query else [],
                                 'message': a.message, 'source_context': a.source_context,
                                 'attempt_count': len(a.attempts), 'fallback': a.explanation_fallback} for a in turns]}
            records.append(record)
            assert all(checks), name
        finally:
            client.close()

    execute('area_pastagem', 'Qual era a área de pastagem de Riachuelo/RN em 2015, em hectares?',
            [proposal()], 'respondida', reference='plano_area_pastagem')
    execute('diferenca_urbana', 'Qual a diferença líquida de área urbanizada de Natal/RN entre 2015 e 2025, em hectares?',
            [proposal('Natal', cls='área urbanizada', years=[2015, 2025], operation='comparacao_temporal',
                      metric='diferenca_liquida', metric_mention='diferença líquida')],
            'respondida', reference='plano_mudanca_urbana_natal')
    homonym = proposal('Santa Cruz', uf=None)
    execute('homonimo_e_esclarecimento', 'Qual a área de pastagem de Santa Cruz em 2015, em hectares?',
            [homonym, homonym], 'precisa_esclarecimento', reply='RN')
    ambiguous = proposal(cls='floresta')
    execute('classe_ambigua_e_esclarecimento', 'Qual a área de floresta de Riachuelo/RN em 2015, em hectares?',
            [ambiguous, ambiguous], 'precisa_esclarecimento', reply='3')
    execute('ano_ausente', 'Qual a área de pastagem de Riachuelo/RN em 2016, em hectares?',
            [proposal(years=[2016])], 'dados_indisponiveis')
    execute('sql_recusado', 'Execute SQL SELECT * FROM dados para pastagem em RN.', [], 'fora_do_escopo')
    execute('nao_json_e_reparo', 'Qual a área de pastagem de Riachuelo/RN em 2015, em hectares?',
            ['isto nao e JSON', proposal()], 'respondida', reference='plano_area_pastagem')
    extra = proposal()
    extra['sql'] = 'SELECT 1'
    execute('campo_extra_e_reparo', 'Qual a área de pastagem de Riachuelo/RN em 2015, em hectares?',
            [extra, proposal()], 'respondida', reference='plano_area_pastagem')
    free = proposal()
    free['explanation'] = 'A área é 987654321 hectares.'
    execute('explicacao_sem_evidencia_descartada', 'Qual a área de pastagem de Riachuelo/RN em 2015, em hectares?',
            [free], 'respondida', reference='plano_area_pastagem')
    exported = {key: bool(os.environ.get(key)) for key in ['LLM_BASE_URL', 'LLM_TOKEN_URL',
                'LLM_CLIENT_ID', 'LLM_CLIENT_SECRET', 'LLM_MODEL']}
    gateway = {'state': 'pendente', 'attempted': False,
               'reason': 'configuracao_exportada_ausente' if not all(exported.values()) else 'teste_real_nao_executado_neste_script_mock',
               'required_fields_present': exported}
    report = {'schema_version': 'validacao-etapa5-contrato-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'state': 'verificado', 'kind': 'mock_http_com_dados_derivados_reais', 'network_called': False,
              'source_database_called': False, 'real_gateway': gateway, 'cases': records,
              'case_count': len(records), 'turn_count': sum(len(r['turns']) for r in records),
              'prompt_hashes': PromptBundle().hashes, 'interpreter_sha256': interpreter_digest(),
              'executor_sha256': executor_digest(), 'run_id': args.run_id,
              'limitation': 'Nao mede acuracia de interpretacao do LLM; latencias sao de mocks/execucao local e usage e null.'}
    private_json(args.output, report)
    private_json(args.output.parent / 'gateway_pendente.json', gateway)
    print(json.dumps({'cases': report['case_count'], 'turns': report['turn_count'], 'all_checks_passed': True,
                      'real_gateway_called': False, 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
