# PDV Word Mecânica — Siliro Tech

**Aplicativo independente para oficinas de carros e motos.** Este repositório não utiliza nem modifica o código do PDV Word Mercado.

## Versão 1.1.0 — avaliação operacional

Interface desktop em Python/Tkinter, armazenamento local SQLite, sem servidor. Código da versão anterior incluído no pacote fonte. Módulos para cadastros de clientes e veículos, orçamentos com itens, ordens de serviço, estoque de peças, mecânicos, agenda, checklist, caixa e relatórios. Abre uma mensagem para revisão e envio manual via WhatsApp.

**Atenção:** não é uma versão comercial homologada. Não realiza NF-e/NFC-e/NFS-e, TEF, aprovação eletrônica verificável, controle de acesso ou auditoria robusta. Precisa de testes de aceitação, segurança, migração e recuperação antes de produção.

## Como obter o instalador Windows

1. Vá em **Actions** → **Gerar instalador Windows**.
2. Abra a execução mais recente após a publicação ou use **Run workflow**.
3. Se a execução finalizar com sucesso, baixe o artefato `PDVWord-Mecanica-Setup-1.1.0` e extraia `PDVWord_Mecanica_Setup_1.1.0.exe`.
4. O Setup é instalado por dois cliques e o computador de destino não exige Python.

A automação compila o programa no GitHub Windows runner com Python 3.12, PyInstaller e Inno Setup 6.

## Dados no Windows

`%LOCALAPPDATA%\PDVWordMecanica\mecanica.db`

As fotos de checklists ficam em `%LOCALAPPDATA%\PDVWordMecanica\fotos`. Faça backup dos **dois**.

## Desenvolvedor

Siliro Tech — projeto separado do PDV Word de mercado.

Código em avaliação: não utilizar com informações reais de clientes sem validação adequada.
