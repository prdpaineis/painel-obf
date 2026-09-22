#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor do Painel OBF - Odoo MMP via XML-RPC.

Escopo: SOMENTE as acoes PENDENTES (state = 'i') das tres etapas da esteira.

    1601  Triar obrigacao
     837  Solicitar obrigacao
     838  Verificar obrigacao

Tudo que o painel mostra sai dessas linhas: quando foram criadas (o SLA),
de quem esta a bola, o que voltou recusado e por que, e por grupo.

Gera dados/painel_obf.json, consumido por painel_obf.html.
SOMENTE LEITURA - nenhum write/create/unlink.
"""
import os, re, sys, json, unicodedata, xmlrpc.client
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict, Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
ENV_CANDIDATOS = [
    BASE / "odoo-mmp_generico.env",
    Path("D:/Gabriel/Área de Trabalho/ACESSO MMP/odoo-mmp_generico.env"),
    Path.home() / ".secrets" / "odoo-mmp.env",
]

ACOES = {1601: "Triar OBF", 837: "Solicitar OBF", 838: "Verificar OBF"}
L = "project.task.action.line"


# ---------------------------------------------------------------- conexao
def carregar_env():
    for p in ENV_CANDIDATOS:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return p
    # CI (GitHub Actions): sem arquivo .env, credenciais vem de Secrets do repo
    if all(k in os.environ for k in ("ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_PASSWORD")):
        return None
    raise SystemExit("Arquivo .env do Odoo nao encontrado.")


env_usado = carregar_env()
URL = os.environ["ODOO_URL"].rstrip("/")
DB = os.environ["ODOO_DB"]
PW = os.environ["ODOO_PASSWORD"]

UID = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/common").authenticate(
    DB, os.environ["ODOO_LOGIN"], PW, {})
if not UID:
    raise SystemExit("Falha de autenticacao no Odoo.")
_M = xmlrpc.client.ServerProxy(URL + "/xmlrpc/2/object", allow_none=True)


def x(model, method, *args, **kw):
    return _M.execute_kw(DB, UID, PW, model, method, list(args), kw)


def log(msg):
    print(msg, flush=True)


def nome(v, default=""):
    return v[1] if v else default


_CTRL = re.compile("[" + "".join(chr(c) for c in list(range(0, 9)) + [11, 12]
                                 + list(range(14, 32))) + "]")


def txt(v, n=400):
    """Texto livre do Odoo: sem caracteres de controle, sem lixo de export."""
    if not v:
        return ""
    s = _CTRL.sub(" ", v)
    s = s.replace("_x000D_", " ").replace("¿", "-")
    return re.sub(r"\s+", " ", s).strip()[:n]


def _read_tolerante(model, ids, fields):
    """O Odoo 10 devolve XML invalido quando um texto traz caracteres de
    controle. Divide ao meio ate isolar o registro ruim e segue sem ele."""
    try:
        return x(model, "read", ids, fields=fields)
    except Exception:
        if len(ids) == 1:
            log("    ! %s.%s ilegivel (XML invalido) - ignorado" % (model, ids[0]))
            return []
        meio = len(ids) // 2
        return _read_tolerante(model, ids[:meio], fields) + \
               _read_tolerante(model, ids[meio:], fields)


def ler_em_lotes(model, ids, fields, tam=200):
    out = []
    for i in range(0, len(ids), tam):
        out.extend(_read_tolerante(model, ids[i:i + tam], fields))
    return out


HOJE = date.today()


def dias_ate(dt_str):
    """Dias de hoje ate a data (negativo = ja passou)."""
    if not dt_str:
        return None
    try:
        return (datetime.strptime(dt_str[:10], "%Y-%m-%d").date() - HOJE).days
    except Exception:
        return None


def bucket_idade(d):
    if d is None:
        return "sem data"
    if d <= 7:
        return "0-7 dias"
    if d <= 15:
        return "8-15 dias"
    if d <= 30:
        return "16-30 dias"
    if d <= 60:
        return "31-60 dias"
    if d <= 90:
        return "61-90 dias"
    return "90+ dias"


# ------------------------------------------------- leitura da resposta do banco
def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower().strip()


def classifica_resposta(pendencia):
    """
    `cumprimento_pendencia` e texto livre, mas na pratica segue o padrao
    "<Status> - <Motivo>: <detalhe>" preenchido pela area do cliente.
    Devolve (status, motivo_bruto).
    """
    p = pendencia.strip()
    if not p:
        return "Sem resposta", ""
    cabeca = p.split(" - ")[0].split(":")[0].strip()
    n = sem_acento(cabeca)
    resto = p[len(cabeca):].lstrip(" -").strip()
    motivo = resto.split(":")[0].split(">")[0].strip(" .")
    # nem todo mundo preenche a taxonomia; frase solta nao vira categoria
    if len(motivo) > 60 or len(motivo.split()) > 8:
        motivo = "Outro (texto livre)"

    if n.startswith("recusad"):
        return "Recusada", motivo
    if n.startswith("cancelad"):
        return "Cancelada", motivo
    if n.startswith("analisando"):
        return "Analisando", motivo
    if n.startswith("cumprindo"):
        return "Cumprindo", motivo
    if n == "ok":
        return "OK", ""
    return "Observacao", ""


def canoniza(motivos):
    """
    Os motivos vem digitados a mao ("Ajuste de informacoes sistemicas" x
    "Ajustes de Informacoes sistemicas"). Agrupa pela forma sem acento e
    elege a grafia mais frequente como rotulo.
    """
    baldes = defaultdict(Counter)
    for m in motivos:
        if m:
            baldes[chave_motivo(m)][m] += 1
    return {k: c.most_common(1)[0][0] for k, c in baldes.items()}


def chave_motivo(m):
    """Une 'Ajuste' e 'Ajustes', 'sistemica' e 'sistemicas' etc."""
    palavras = [w[:-1] if len(w) > 4 and w.endswith("s") else w
                for w in re.findall(r"\w+", sem_acento(m))]
    return " ".join(palavras)


# ------------------------------------------------------------------- de quem e
def de_quem(acao, tipo_pendencia, status):
    """
    Em que mao esta a bola:
      cliente  - solicitado, esperando o banco responder
      nos      - e nossa vez de agir (triar, solicitar, tratar recusa)
      ok       - cliente ja respondeu OK, falta so fechar a verificacao
    """
    if status in ("Recusada", "Cancelada"):
        return "nos"
    if acao in (1601, 837):
        return "nos"
    n = sem_acento(tipo_pendencia)
    if n == "solicitado":
        return "cliente"
    if n == "contabilizado":
        return "ok"
    if n == "analise":
        return "nos"
    return "nos"


# ---------------------------------------------------------------------- coleta
log("Odoo: %s  uid=%s  env=%s" % (URL, UID, env_usado.name if env_usado else "CI (Secrets)"))
log("Escopo: acoes PENDENTES (state='i') de Triar / Solicitar / Verificar OBF\n")

CAMPOS = ["id", "action_id", "grupo_id", "dossie_id", "task_id", "user_id",
          "create_date", "write_date", "date_deadline", "stage_id",
          "cumprimento_pendencia", "cumprimento_tipo_pendencia_id",
          "cumprimento_situacao_id", "cumprimento_obrigacao_resultado",
          "cumprimento_data_prazo", "cumprimento_subtipo_id",
          "cumprimento_produto_id", "cumprimento_numero_contrato",
          "cumprimento_obrigacao", "cumprimento_lote",
          "cumprimento_multa_tem", "cumprimento_desobediencia_tem"]

brutos = []
for aid, nm in ACOES.items():
    ids = x(L, "search", [("action_id", "=", aid), ("state", "=", "i")], limit=0)
    log("[1/3] %-16s %d pendentes" % (nm, len(ids)))
    for r in ler_em_lotes(L, ids, CAMPOS):
        r["_acao"] = aid
        brutos.append(r)

# motivos precisam de uma passada previa para eleger a grafia canonica
respostas = [classifica_resposta(txt(r.get("cumprimento_pendencia"))) for r in brutos]
mapa_motivo = canoniza(m for _, m in respostas)

log("\n[2/3] enriquecendo os casos...")
dossies = sorted({r["dossie_id"][0] for r in brutos if r.get("dossie_id")})
mapa_dossie = {}
for r in ler_em_lotes("dossie.dossie", dossies,
                      ["id", "name", "processo", "carteira_id", "fase_id", "estado_id"]):
    mapa_dossie[r["id"]] = {
        "caso": txt(r.get("name"), 60),
        "processo": txt(r.get("processo"), 40),
        "carteira": nome(r.get("carteira_id")),
        "fase": nome(r.get("fase_id")),
        "uf": nome(r.get("estado_id")),
    }
log("    %d casos" % len(mapa_dossie))

log("\n[3/3] montando as linhas...")
pendentes = []
for r, (status, motivo_bruto) in zip(brutos, respostas):
    aid = r["_acao"]
    pend_txt = txt(r.get("cumprimento_pendencia"))
    tipo_pend = nome(r.get("cumprimento_tipo_pendencia_id"))
    motivo = mapa_motivo.get(chave_motivo(motivo_bruto), "") if motivo_bruto else ""
    idade = -(dias_ate(r.get("create_date")) or 0) if r.get("create_date") else None
    prazo = r.get("cumprimento_data_prazo") or r.get("date_deadline") or ""
    dias_prazo = dias_ate(prazo)
    d = mapa_dossie.get(r["dossie_id"][0] if r.get("dossie_id") else None,
                        {"caso": "", "processo": "", "carteira": "", "fase": "", "uf": ""})

    pendentes.append({
        "linha_id": r["id"],
        "acao": aid,
        "grupo": nome(r.get("grupo_id"), "(sem grupo)"),
        "grupo_id": r["grupo_id"][0] if r.get("grupo_id") else 0,
        "dossie_id": r["dossie_id"][0] if r.get("dossie_id") else None,
        "caso": d["caso"], "processo": d["processo"],
        "carteira": d["carteira"], "fase": d["fase"], "uf": d["uf"],
        "responsavel": nome(r.get("user_id"), "(sem responsavel)"),
        "estagio": nome(r.get("stage_id")),
        "criado_em": (r.get("create_date") or "")[:10],
        "mes": (r.get("create_date") or "")[:7],
        "idade_dias": idade,
        "faixa_idade": bucket_idade(idade),
        "prazo": prazo,
        "dias_prazo": dias_prazo,
        "vencido": dias_prazo is not None and dias_prazo < 0,
        "status": status,                 # resposta do banco
        "motivo": motivo,                 # por que recusou / cancelou
        "pendencia_txt": pend_txt,
        "tipo_pendencia": tipo_pend,
        "bola": de_quem(aid, tipo_pend, status),
        "subtipo": nome(r.get("cumprimento_subtipo_id")),
        "produto": nome(r.get("cumprimento_produto_id")),
        "contrato": txt(r.get("cumprimento_numero_contrato"), 60),
        "lote": txt(r.get("cumprimento_lote"), 30),
        "obrigacao": txt(r.get("cumprimento_obrigacao"), 300),
        "risco_multa": r.get("cumprimento_multa_tem") == "sim",
        "risco_desobediencia": r.get("cumprimento_desobediencia_tem") == "sim",
    })

grupos = [g for g, _ in Counter(p["grupo"] for p in pendentes).most_common()]

dados = {
    "gerado_em": datetime.now().isoformat(timespec="seconds"),
    "escopo": "acoes pendentes (state='i') das etapas Triar / Solicitar / Verificar OBF",
    "acoes": {str(k): v for k, v in ACOES.items()},
    "grupos": grupos,
    "pendentes": pendentes,
}

out_dir = BASE / "dados"
out_dir.mkdir(exist_ok=True)
blob = json.dumps(dados, ensure_ascii=False)
(out_dir / "painel_obf.json").write_text(blob, encoding="utf-8")
(out_dir / ("painel_obf_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
 ).write_text(blob, encoding="utf-8")

# ------------------------------------------------------------------- resumo
log("\n" + "=" * 64)
log("Fila pendente: %d acoes" % len(pendentes))
log("\n  por etapa:")
for aid, nm in ACOES.items():
    log("    %-16s %5d" % (nm, sum(1 for p in pendentes if p["acao"] == aid)))
log("\n  de quem esta a bola:")
for k, rot in (("nos", "conosco"), ("cliente", "com o cliente"), ("ok", "respondida OK")):
    log("    %-16s %5d" % (rot, sum(1 for p in pendentes if p["bola"] == k)))
log("\n  resposta do banco:")
for k, n in Counter(p["status"] for p in pendentes).most_common():
    log("    %-16s %5d" % (k, n))
log("\n  motivos de recusa / cancelamento:")
for k, n in Counter(p["motivo"] for p in pendentes
                    if p["status"] in ("Recusada", "Cancelada") and p["motivo"]).most_common(12):
    log("    %5d  %s" % (n, k[:60]))
log("\n  prazo: %d vencidos | %d sem prazo"
    % (sum(1 for p in pendentes if p["vencido"]),
       sum(1 for p in pendentes if p["dias_prazo"] is None)))
log("\nOK -> %s" % (out_dir / "painel_obf.json"))
