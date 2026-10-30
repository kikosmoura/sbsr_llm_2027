"""Sessao explicita por UUID, lock e persistencia atomica local; sem historico global."""
import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

class SessionError(ValueError):pass


def private_text(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w") as f:f.write(text)
    os.chmod(tmp,0o600);os.replace(tmp,path)

def private_json(path,value):
    private_text(path,json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False))

class DialogueStore:
    def __init__(self,root,project):
        self.sessions=Path(root)/project.data_dir/"dialogues"
        self.audit=Path(root)/project.artifacts_dir/"dialogues"
    @contextmanager
    def open(self,session_id,reply_to,identity,max_turns):
        supplied=session_id is not None
        session_id=session_id or uuid4().hex
        if not re.fullmatch(r"[0-9a-f]{32}",session_id):raise SessionError("sessao_invalida")
        if reply_to and not re.fullmatch(r"[0-9a-f]{32}",reply_to):raise SessionError("esclarecimento_invalido")
        self.sessions.mkdir(parents=True,exist_ok=True)
        with (self.sessions/(session_id+".lock")).open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            path=self.sessions/(session_id+".json")
            if supplied:
                if not path.is_file():raise SessionError("sessao_nao_encontrada")
                if path.stat().st_size>524288:raise SessionError("sessao_excede_limite")
                state=json.loads(path.read_text())
                if state.get("identity")!=identity:raise SessionError("contexto_da_sessao_incompativel")
                pending=state.get("pending")
                if not reply_to or not pending or pending["clarification_id"]!=reply_to:raise SessionError("resposta_exige_esclarecimento_pendente_da_mesma_sessao")
            else:
                if reply_to:raise SessionError("esclarecimento_sem_sessao")
                state={"schema_version":"sessao-perguntas-v1","session_id":session_id,"identity":identity,"original_question":None,"bindings":{},"pending":None,"turn_ids":[]}
            if len(state["turn_ids"])>=max_turns:raise SessionError("limite_de_turnos_da_sessao")
            yield state,path
    def reject(self,answer):
        private_json(self.audit/answer.session_id/(answer.turn_id+".json"),answer.model_dump(mode="json"))
    def commit(self,state,path,answer):
        state["turn_ids"].append(answer.turn_id)
        state["pending"]=answer.clarification.model_dump(mode="json") if answer.clarification else None
        state["parent_turn_id"]=answer.turn_id
        private_json(self.audit/answer.session_id/(answer.turn_id+".json"),answer.model_dump(mode="json"))
        private_json(path,state)
