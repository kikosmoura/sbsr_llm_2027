import hashlib
import json
from pathlib import Path
from string import Template
from ..semantics.catalog import digest
from .dialogue_models import ModelProposal

class PromptBundle:
    version="pt_v3"
    def __init__(self):
        root=Path(__file__).parent/"prompts"/self.version
        self.files={name:(root/name).read_text() for name in ["system.txt","user.txt","repair.txt","proposal.schema.json"]}
        if json.loads(self.files["proposal.schema.json"])!=ModelProposal.model_json_schema():raise ValueError("schema_prompt_divergente")
        self.hashes={name:hashlib.sha256(text.encode()).hexdigest() for name,text in self.files.items()}
    def messages(self,question,context,issues=None):
        encoded=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
        messages=[{"role":"system","content":self.files["system.txt"]},
            {"role":"user","content":Template(self.files["user.txt"]).substitute(question_json=encoded(question),context_json=encoded(context),schema_json=self.files["proposal.schema.json"])}]
        if issues is not None:
            messages.append({"role":"user","content":Template(self.files["repair.txt"]).substitute(issues_json=encoded(issues))})
        return messages


def interpreter_digest():
    base=Path(__file__).parents[1]
    files=sorted([*base.joinpath("llm").glob("*.py"),base/"storage/dialogues.py",base/"semantics/validation.py"])
    return digest({str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
