# Agente Leitor de XML Fiscal (NF-e) — Streamlit

## O que faz
- Upload de **XML(s) de NF-e** ou **ZIP** com vários XMLs
- Leitura do cabeçalho (emitente, destinatário, chave, número, série, data, vNF)
- Leitura dos itens (produtos) e campos principais: **NCM, CFOP, CST/CSOSN, qCom, vUnCom, vProd**
- Gera **Consolidado** por agrupamento
- Exporta **Excel** com abas: Cabecalho_NFe (opcional), Itens_Bruto, Consolidado

## Segurança (Login)
- O app exige login.
- Usuários ficam em `data/users.json` com senha em **hash PBKDF2**.
- Admin pode criar/desativar usuários na página **Admin** (menu lateral).

> **IMPORTANTE:** troque a senha padrão do admin antes de usar com clientes.

## Como rodar LOCAL (Windows)
1. Instale Python 3.10+ (recomendado 3.11)
2. No Windows, dê duplo clique em `run.bat`

## Como rodar LOCAL (Linux/Mac)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/app.py
```

## Configurar Admin por secrets (recomendado)
Crie `.streamlit/secrets.toml`:

```toml
ADMIN_USER="admin"
ADMIN_PASS="sua_senha_forte_aqui"
```

## Deploy no Streamlit Community Cloud
- Suba o repositório no GitHub
- No Streamlit Cloud, aponte para `app/app.py`
- Em **Secrets**, adicione `ADMIN_USER` e `ADMIN_PASS`

> Observação: `.bat` é apenas para execução local no Windows.

## v2 — Validação Fiscal + Base Legal gerenciável

- ✅ Tela de **Login** (usuário/senha) + **Admin** para criar/inativar usuários.
- ✅ Leitura de XML/ZIP e exportação Excel.
- ✅ **Validação CFOP/NCM/CST/CSOSN** baseada em planilhas de Base Legal.
- ✅ Página **📚 Admin — Base Legal** (somente admin) para upload das planilhas.

### Base Legal (planilhas)
Os arquivos vigentes ficam em `data/base_legal/current/`.
- `ncm_regras.xlsx` (colunas: `ncm`, `descricao`)
- `cfop_regras.xlsx` (colunas: `cfop`, `descricao`)
- `cst_csosn_regras.xlsx` (colunas: `codigo`, `tipo` [CST/CSOSN], `descricao`)

Ao fazer upload pela página Admin, o app cria backup em `data/base_legal/history/`.
