# Painel OBF — a fila de Obrigação de Fazer

Foto das ações **pendentes** das três etapas da esteira de OBF no Odoo MMP:
**Triar**, **Solicitar** e **Verificar obrigação**.

Só fila pendente. Nada de histórico, nada de concluído ou cancelado.

## Link público

https://prdpaineis.github.io/painel-obf/ — atualizado sozinho todo dia às
07:00 (BRT) via GitHub Actions (`.github/workflows/atualizar-painel.yml`).
Sem autenticação: qualquer pessoa com o link vê os dados.

## Como atualizar manualmente

```bash
cd docs
py -3 coletar_obf.py && py -3 gerar_painel.py
```

Depois abra `docs/index.html` com duplo clique. O HTML é autossuficiente
(dados embutidos), não precisa de servidor nem de internet.

| arquivo | o que faz |
|---|---|
| `docs/coletar_obf.py` | Lê o Odoo por XML-RPC e grava `docs/dados/painel_obf.json` (+ cópia com timestamp). **Somente leitura.** |
| `docs/gerar_painel.py` | Injeta o JSON no template e gera `docs/index.html`. |
| `docs/template_painel.html` | O painel em si (HTML/CSS/JS). Mexa aqui para mudar layout ou gráficos. |
| `docs/dados/` | Snapshots locais, nunca versionados. |

`docs/` é a raiz servida pelo GitHub Pages.

## Credenciais

Local: copie `docs/odoo-mmp_generico.env.example` para
`docs/odoo-mmp_generico.env` e preencha. O coletor procura nessa ordem: essa
pasta, depois `..\ACESSO MMP\`, depois `~/.secrets/odoo-mmp.env`.

O `.gitignore` bloqueia `*.env`. **Nunca commite o arquivo preenchido.**

No CI (GitHub Actions), as credenciais vêm dos Secrets do repositório
(`ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`) — sem arquivo `.env`.

## O que este repositório versiona (e o que não)

**Público e versionado, de propósito:** `docs/index.html`, gerado todo dia com
número de processo, nome de caso e parte de clientes reais embutidos.

**Fora do repositório:** `docs/dados/` (snapshots brutos do coletor) e
qualquer `.env`. Quem clonar roda o coletor local e gera os próprios.

## O que cada número significa

A esteira mora em `project.task.action.line`, com `state = 'i'` (Pendente):

| ação | `action_id` |
|---|---|
| Triar obrigação | 1601 |
| Solicitar obrigação | 837 |
| Verificar obrigação | 838 |

- **Quando entrou** — `create_date` da própria ação pendente. É o SLA: mês antigo
  com barra alta é atraso acumulado, não volume de trabalho.
- **Prazo** — `cumprimento_data_prazo`, com o `date_deadline` da ação como reserva.
  Negativo quer dizer vencido.
- **Grupo** — `grupo_id` da própria linha de ação (`res.partner`).

### Resposta do cliente

Sai do campo texto `cumprimento_pendencia`, que a área do banco preenche no
padrão `Status - Motivo: detalhe`. O coletor lê o status (**Recusada**,
**Cancelada**, Analisando, Cumprindo, OK) e o motivo.

Quem escreveu fora do padrão cai em *Observação*; motivo em frase solta vira
*Outro (texto livre)* — melhor do que inventar categoria. Grafias diferentes do
mesmo motivo ("Ajuste" / "Ajustes de informações sistêmicas") são unidas por
`chave_motivo()`.

> Só a etapa **Verificar** tem resposta. Triar e Solicitar ainda nem foram ao
> cliente — por isso as colunas de recusa ficam zeradas nessas duas.

### De quem está a bola

| valor | quando |
|---|---|
| `cliente` | `cumprimento_tipo_pendencia_id` = Solicitado e o banco ainda não recusou |
| `ok` | Contabilizado — cliente respondeu OK, falta só fechar a verificação |
| `nos` | todo o resto: a fila inteira de Triar e Solicitar, mais tudo que voltou recusado ou cancelado |

## Limites conhecidos

- A tabela da fila mostra 300 linhas na tela; o botão de CSV baixa tudo.
- O eixo de "quando entrou" agrupa em uma coluna só tudo que é mais velho que
  12 meses (`MESES_EIXO` no template).
- Alguns registros devolvem XML inválido pelo servidor (caractere de controle em
  campo texto). O coletor isola e segue sem eles, avisando no log.
- O coletor entra com o usuário configurado no `.env`, então enxerga o recorte de
  permissão da empresa desse usuário.
