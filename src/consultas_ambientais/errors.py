"""Classifica erros locais sem retornar mensagens que possam conter segredos."""


def network_issue(error):
    message=str(error).lower()
    if any(s in message for s in ["temporary failure in name resolution","name or service not known","nameresolutionerror"]):
        return "falha_resolucao_dns"
    if any(s in message for s in ["operation not permitted","permission denied"]):
        return "bloqueio_rede_ambiente"
    if any(s in message for s in ["network is unreachable","no route to host"]):
        return "rede_sem_rota"
    if "connection refused" in message:return "conexao_recusada"
    if "timeout" in message or "timed out" in message:return "timeout"
    return "falha_conexao"
