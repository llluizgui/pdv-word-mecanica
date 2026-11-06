# PDV Word Mecânica 1.5.0 — Atendimento integrado (versão de avaliação)

Sistema desktop Windows 10/11 para oficinas de automóveis e motos, separado do PDV Word de mercados. Banco SQLite local em `%LOCALAPPDATA%\PDVWordMecanica\mecanica.db` (não é apagado na atualização).

## Fluxo unificado

**Atendimento:** numa única aba, selecionar ou salvar cliente, selecionar ou cadastrar veículo, descrever orçamento, adicionar peças/serviços com quantidades e preços (inclusive antes de salvar o orçamento), aprovar/rejeitar e gerar/imprimir PDF. Depois da aprovação, alterações de peças e valores exigem novo orçamento para manter o histórico fiel. A OS é vinculada automaticamente e baixa as peças do estoque apenas uma vez.

**Estoque**, **Mecânicos**, **Ordens de serviço**, **Agenda** e **Checklist** continuam separados. A antiga aba "Itens orçamento" foi removida — os itens agora ficam dentro do Atendimento.

**Caixa:** dentro da mesma aba há dois fluxos separados: venda de múltiplos produtos por nome ou código, com cliente cadastrado ou avulso; e serviço por nome do cliente, placa ou OS, carregando os itens do orçamento e valor devido. O operador pode editar/remover quantidades do carrinho antes da venda. OS aprovada não pode ter valores alterados sem novo orçamento; OS sem pagamentos pode ser cancelada, com devolução de peças ao estoque. Despesas avulsas têm uma área própria. Comprovantes de pagamento e venda são PDFs **NÃO FISCAIS** gerados no próprio computador.

**Relatórios Ctrl+A:** senha criada no primeiro acesso (PBKDF2/SHA-256) protege vendas e recebimentos por dia, semana, mês, ano ou período. Os valores de orçamentos aprovados ficam em **a receber** até que haja efetivo pagamento. Configuração do estabelecimento (nome, CPF/CNPJ, endereço, cidade, telefone) pode ser feita dentro dos relatórios protegidos, em "Dados da oficina (PDFs)". A ficha de orçamento e os comprovantes exibem identificação, data, cliente/veículo e mecânico quando disponível.

## Instalador Windows

O GitHub Actions compila a versão para Windows e publica em Releases como `PDVWord_Mecanica_Setup_1.5.0.exe`. O cliente não precisa de Python. A instalação usa a mesma identidade de aplicativo das versões anteriores e mantém os dados em `%LOCALAPPDATA%` fora da pasta de instalação.

Se gerar no próprio PC, use `GERAR_INSTALADOR_WINDOWS.bat` com Python 3.12, PyInstaller e Inno Setup 6.

## Avisos importantes

- **Não há emissão real de NF-e, NFC-e ou NFS-e, TEF ou conexão com adquirente.** O comprovante **não substitui nota fiscal**. Integração fiscal só pode ser anunciada após implementação, configuração e validação legal da oficina.
- A versão 1.4 é **candidata a testes**, não foi homologada em equipamento real da oficina; faça testes antes de uso comercial e consulte o contador.
- Dados de clientes ficam **apenas no computador local** e não são enviados ao GitHub. Faça backup do banco SQLite e da pasta `fotos`, e teste a recuperação antes de operar.
- Ao executar `Ctrl+A`, evite compartilhar a senha de acesso gerencial. O restante das operações não tem autenticação por perfil nesta versão.

## Dependências de desenvolvimento

Python 3.12 (stdlib `tkinter`, `sqlite3`) e ReportLab 4.4.9 para PDFs. PyInstaller 6.16 + Inno Setup 6 para gerar instalador.

## Interface moderna 1.5
Atendimento unico em cinco etapas: cliente, veiculo, orcamento, itens e revisao.
Menu lateral, resumo dinamico, rolagem em monitores menores e dados locais preservados.
