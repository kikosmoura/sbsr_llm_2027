"""Processo descartavel: timeout total pode encerrar I/O bloqueante de verdade."""
import json
import multiprocessing
import os
from ..llm.dialogue_models import AskAnswer, InterpretationConfig
from .models import DeliveryError


def answer_worker(connection, payload):
    try:
        # Nem bibliotecas nativas podem escrever corpo de erro ou URL privada no servidor.
        with open(os.devnull, 'w') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
        from ..llm.client import GatewayClient
        from ..llm.conversation import ConversationService
        from ..llm.privacy import Redactor
        root, project, config, environment, question, session, clarification = payload
        settings = environment.settings
        client = GatewayClient(settings) if settings.configured else None
        try:
            service = ConversationService(root, project, config.run_id, root / config.territories,
                                          root / config.capabilities, client, settings,
                                          InterpretationConfig(max_output_tokens=config.llm_max_tokens))
            service.redactor = Redactor([*service.redactor.secrets, *environment.redaction_secrets])
            answer = service.ask(question, session, clarification)
            encoded = answer.model_dump_json().encode()
            connection.send_bytes(encoded if len(encoded) <= config.max_result_bytes else b'{}')
        finally:
            if client:
                client.close()
    except Exception:
        try:
            connection.send_bytes(b'{}')
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class ProcessRunner:
    def __init__(self, target=answer_worker):
        self.target = target

    def __call__(self, root, project, config, environment, question, session=None, clarification=None):
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=self.target, args=(sender, (
            root, project, config, environment, question, session, clarification)), daemon=True)
        try:
            process.start()
            sender.close()
            if not receiver.poll(config.max_query_seconds):
                raise DeliveryError('consulta_timeout', 504)
            raw = receiver.recv_bytes(config.max_result_bytes)
            return AskAnswer.model_validate_json(raw)
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError('falha_no_processo_de_consulta') from None
        finally:
            receiver.close()
            sender.close()
            if process.pid is not None:
                process.join(timeout=.1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
                process.close()
