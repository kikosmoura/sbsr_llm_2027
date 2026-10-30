"""Obtem somente o ODT oficial identificado em configs/science (TLS verificado)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests


def obtain(template, output, session):
    """No maximo 1 MiB; nao substitui um arquivo divergente nem aceita outra revisao."""
    output = Path(output)
    expected = template['sha256']
    if output.exists():
        if hashlib.sha256(output.read_bytes()).hexdigest() != expected:
            raise ValueError('arquivo_existente_divergente')
        return 'cache_verificado'
    chunks = []
    size = 0
    with session.get(template['url'], stream=True, timeout=(10, 30), verify=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(16384):
            size += len(chunk)
            if size > 1024 * 1024:
                raise ValueError('limite_de_bytes_excedido')
            chunks.append(chunk)
    content = b''.join(chunks)
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('revisao_diferente_requer_nova_conferencia_das_normas')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Modo exclusivo: nao sobrescreve mudancas concorrentes nem cria URL assinada.
    with output.open('xb') as destination:
        destination.write(content)
    return 'obtido_e_hash_verificado'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/scientific/fontes_sbsr2027/template_oficial.odt'))
    args = parser.parse_args()
    rules = Path(__file__).resolve().parent.parent / 'configs/science/normas_verificadas.json'
    try:
        template = json.loads(rules.read_text())['template']
        with requests.Session() as session:
            state = obtain(template, args.output, session)
        print(json.dumps({'state': state, 'sha256': template['sha256']}))
    except (requests.RequestException, OSError, ValueError, KeyError):
        # Nao exibir URL de proxy, corpo HTTP ou detalhes locais de configuracao.
        print('Nao foi possivel obter/verificar o template; arquivo existente preservado.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
