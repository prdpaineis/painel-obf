#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monta index.html a partir de dados/painel_obf.json + template_painel.html.
O HTML fica autossuficiente (dados embutidos) e e servido pelo GitHub Pages.
"""
import json, sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
ORIGEM = BASE / "dados" / "painel_obf.json"
TEMPLATE = BASE / "template_painel.html"
DESTINO = BASE / "index.html"

d = json.loads(ORIGEM.read_text(encoding="utf-8"))
pend = d["pendentes"]

# chaves curtas: o JSON vai inteiro para dentro do HTML
linhas = [{
    "a": p["acao"], "g": p["grupo"],
    "caso": p["caso"], "proc": p["processo"], "uf": p["uf"], "fase": p["fase"],
    "sub": p["subtipo"], "prod": p["produto"], "ct": p["contrato"], "lt": p["lote"],
    "cri": p["criado_em"], "m": p["mes"], "d": p["idade_dias"], "fx": p["faixa_idade"],
    "prazo": p["prazo"], "dp": p["dias_prazo"], "v": p["vencido"],
    "st": p["status"], "mo": p["motivo"], "pt": p["pendencia_txt"], "b": p["bola"],
    "mul": p["risco_multa"], "des": p["risco_desobediencia"], "resp": p["responsavel"],
} for p in pend]

n = len(linhas)
por_etapa = Counter(p["acao"] for p in pend)
nf = lambda v: "{:,}".format(v).replace(",", ".")

metodologia = (
    "Fonte: Odoo MMP (<code>mmp.intelligenti.com.br</code>), por XML-RPC, somente leitura. "
    "<strong>O painel inteiro e uma foto das acoes pendentes</strong> &mdash; "
    "<code>project.task.action.line</code> com <code>state = 'i'</code> nas tres etapas: "
    "Triar (<code>action_id</code> 1601, %s na fila), Solicitar (837, %s) e "
    "Verificar (838, %s). Nada de historico, nada de concluido ou cancelado: %s linhas ao todo."
    "<br><br>"
    "<strong>Quando entrou</strong> e o <em>Created on</em> da propria acao pendente. "
    "<strong>Prazo</strong> vem de <code>cumprimento_data_prazo</code>, com o "
    "<em>Deadline</em> da acao como reserva; negativo quer dizer vencido."
    "<br><br>"
    "<strong>Resposta do cliente</strong> sai do campo texto "
    "<code>cumprimento_pendencia</code>, que a area do banco preenche no padrao "
    "&ldquo;Status - Motivo: detalhe&rdquo;. O painel le o status (Recusada, Cancelada, "
    "Analisando, Cumprindo, OK) e o motivo. Quem escreveu fora do padrao cai em "
    "<em>Observacao</em>, e motivo em frase solta vira <em>Outro (texto livre)</em> &mdash; "
    "preferimos isso a inventar categoria. Grafias diferentes do mesmo motivo "
    "(&ldquo;Ajuste&rdquo; / &ldquo;Ajustes de informacoes sistemicas&rdquo;) sao unidas."
    "<br><br>"
    "<strong>De quem esta a bola</strong>: <em>com o cliente</em> quando "
    "<code>cumprimento_tipo_pendencia_id</code> = Solicitado e o banco ainda nao recusou; "
    "<em>respondida OK</em> quando esta Contabilizado; <em>conosco</em> no resto &mdash; "
    "toda a fila de Triar e de Solicitar, mais tudo que voltou recusado ou cancelado."
    "<br><br>"
    "<strong>Grupo</strong> e o <code>grupo_id</code> da propria linha de acao. "
    "O coletor entra com o usuario configurado no .env, entao enxerga o recorte "
    "de permissao da empresa desse usuario."
) % (nf(por_etapa[1601]), nf(por_etapa[837]), nf(por_etapa[838]), nf(n))

payload = {
    "gerado_em": d["gerado_em"],
    "escopo": d["escopo"],
    "grupos": d["grupos"],
    "pend": linhas,
    "metodologia": metodologia,
}

html = TEMPLATE.read_text(encoding="utf-8")
if "/*__DADOS__*/ null" not in html:
    raise SystemExit("Marcador /*__DADOS__*/ nao encontrado no template.")
html = html.replace("/*__DADOS__*/ null",
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
DESTINO.write_text(html, encoding="utf-8")

print("OK -> %s  (%.1f MB)" % (DESTINO, DESTINO.stat().st_size / 1048576))
print("    %d acoes pendentes | %d grupos" % (n, len(d["grupos"])))
print("    recusadas %d | canceladas %d | com o cliente %d | vencidas %d"
      % (sum(1 for p in pend if p["status"] == "Recusada"),
         sum(1 for p in pend if p["status"] == "Cancelada"),
         sum(1 for p in pend if p["bola"] == "cliente"),
         sum(1 for p in pend if p["vencido"])))
