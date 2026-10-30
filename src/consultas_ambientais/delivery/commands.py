"""CLI local e servidor loopback. Chaves nunca sao impressas ou passadas na linha de comando."""
import json
from pathlib import Path
from .settings import LocalSettings, load_environment
from .models import DeliveryError, error_payload
from .export import export
from ..storage.dialogues import private_json, private_text


def add_parsers(sub):
    p = sub.add_parser('local', help='API/CLI local com sessoes protegidas e capacidades verificadas.')
    p.add_argument('--settings', type=Path, default=Path('configs/local.json'))
    p.add_argument('--env-file', type=Path, help='OPT-IN: carregar .env em memoria, sem executar shell.')
    commands = p.add_subparsers(dest='local_action', required=True)
    serve = commands.add_parser('serve', help='FastAPI somente em loopback, um worker; nao publica na internet.')
    serve.add_argument('--port', type=int)
    caps = commands.add_parser('capabilities', help='Somente estatisticas materializadas com hashes verificados.')
    caps.add_argument('--territory-code')
    for name in ['session', 'ask', 'clarify', 'result', 'answer', 'evidence', 'export']:
        q = commands.add_parser(name)
        q.add_argument('--key-file', type=Path, default=Path('data/local_keys/default.json'))
        if name in {'ask', 'clarify'}:
            q.add_argument('--question', required=True)
        if name in {'result', 'answer', 'evidence', 'export', 'clarify'}:
            q.add_argument('--id', required=True, help='result_id; para answer, answer_id.')
        if name == 'clarify':
            q.add_argument('--reply-to', required=True, help='clarification_id do resultado indicado.')
        if name == 'export':
            q.add_argument('--format', choices=['json', 'csv', 'html'], required=True)
            q.add_argument('--output', type=Path, required=True)


def key_path(root, path):
    target = path.resolve()
    if not target.is_relative_to((root/'data/local_keys').resolve()) or any(p.startswith('.env') for p in path.parts):
        raise DeliveryError('arquivo_chave_fora_do_diretorio_privado')
    return target


def run(args, project):
    from .runtime import LocalRuntime
    try:
        root = Path.cwd().resolve()
        cfg = LocalSettings.load(args.settings)
        if args.local_action == 'serve' and args.port is not None:
            cfg = LocalSettings.model_validate({**cfg.model_dump(), 'port': args.port})
        environment = load_environment(cfg, args.env_file)
        runtime = LocalRuntime(root, project, cfg, environment)
        action = args.local_action
        if action == 'serve':
            import uvicorn
            from ..api import create_app
            app = create_app(root, project, cfg, environment)
            uvicorn.run(app, host=cfg.bind_host, port=cfg.port, workers=1, reload=False,
                        access_log=False, log_level='warning', proxy_headers=False,
                        server_header=False, timeout_keep_alive=5,
                        timeout_graceful_shutdown=10, limit_concurrency=16, backlog=16,
                        h11_max_incomplete_event_size=16384)
            return 0
        if action == 'capabilities':
            value = runtime.get_capabilities(args.territory_code)
        else:
            path = key_path(root, args.key_file)
            if action == 'session':
                if path.exists():
                    raise DeliveryError('arquivo_chave_ja_existe', 409)
                session = runtime.create_session()
                private_json(path, session.model_dump(mode='json'))
                value = {'session_id': session.session_id, 'expires_at': session.expires_at.isoformat(),
                         'private_key_file_created': True}
            else:
                if path.stat().st_size > 2048 or path.stat().st_mode & 0o077:
                    raise DeliveryError('arquivo_chave_inseguro')
                key = json.loads(path.read_text())
                sid, token = key['session_id'], key['session_token']
                if action == 'answer':
                    value = runtime.registry.answer(sid, token, args.id).model_dump(mode='json')
                elif action in {'ask', 'clarify'}:
                    response = runtime.ask(sid, token, args.question,
                                           args.id if action == 'clarify' else None,
                                           args.reply_to if action == 'clarify' else None)
                    value = response.model_dump(mode='json')
                else:
                    response = runtime.get(sid, token, args.id)
                    if action == 'export':
                        target = args.output.resolve()
                        if not target.is_relative_to((root/'reports/local').resolve()):
                            raise DeliveryError('exportacao_exige_reports_local')
                        content, _ = export(response, args.format, cfg.max_result_bytes)
                        private_text(target, content)
                        value = {'status': response.status.value, 'result_id': response.result_id,
                                 'format': args.format, 'exported': True}
                    elif action == 'evidence':
                        value = {'status': response.status.value, 'result_id': response.result_id,
                                 'evidence': [e.model_dump(mode='json') for e in response.result.evidence] if response.result else [],
                                 'execution': response.result.execution.model_dump(mode='json') if response.result and response.result.execution else None,
                                 'source_context': response.source_context}
                    else:
                        value = response.model_dump(mode='json')
        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if value.get('status') in {'erro_tecnico', 'dados_indisponiveis', 'fora_do_escopo', 'precisa_esclarecimento'} else 0
    except DeliveryError as error:
        print(json.dumps(error_payload(error.reason, error.status), ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps(error_payload('falha_configuracao_ou_operacao_local'), ensure_ascii=False))
        return 2
